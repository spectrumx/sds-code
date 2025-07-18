import datetime
import uuid
import zipfile
from pathlib import Path
from typing import Any

import redis
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail import send_mail
from django.template.loader import render_to_string
from loguru import logger
from redis import Redis

from sds_gateway.api_methods.helpers.download_file import download_file
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import TemporaryZipFile
from sds_gateway.api_methods.models import user_has_access_to_item
from sds_gateway.api_methods.utils.sds_files import sanitize_path_rel_to_user
from sds_gateway.users.models import User


def get_redis_client() -> Redis:
    """Get Redis client for locking."""
    return Redis.from_url(settings.CELERY_BROKER_URL)


def send_email(
    subject,
    recipient_list,
    plain_template=None,
    html_template=None,
    context=None,
    plain_message=None,
    html_message=None,
):
    """
    Generic utility to send an email with optional template rendering.
    Args:
        subject: Email subject
        recipient_list: List of recipient emails
        plain_template: Path to plain text template (optional)
        html_template: Path to HTML template (optional)
        context: Context for rendering templates (optional)
        plain_message: Raw plain text message (optional, overrides template)
        html_message: Raw HTML message (optional, overrides template)
    """
    from django.conf import settings

    if not recipient_list:
        return False
    if not plain_message and plain_template and context:
        plain_message = render_to_string(plain_template, context)
    if not html_message and html_template and context:
        html_message = render_to_string(html_template, context)
    send_mail(
        subject=subject,
        message=plain_message or "",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipient_list,
        html_message=html_message,
    )
    return True


def acquire_user_lock(user_id: str, task_name: str, timeout: int = 300) -> bool:
    """
    Acquire a Redis lock for a user to ensure only one task runs at a time.

    Args:
        user_id: The user's ID
        task_name: Name of the task (e.g., 'dataset_download')
        timeout: Lock timeout in seconds (default: 5 minutes)

    Returns:
        bool: True if lock acquired, False if already locked
    """
    redis_client = get_redis_client()
    lock_key = f"user_lock:{user_id}:{task_name}"

    try:
        # Try to acquire the lock with a timeout
        acquired = redis_client.set(
            lock_key,
            datetime.datetime.now(datetime.UTC).isoformat(),
            ex=timeout,
            nx=True,
        )
        return bool(acquired)
    except (redis.RedisError, ConnectionError) as e:
        logger.error(f"Error acquiring lock for user {user_id}: {e}")
        return False


def release_user_lock(user_id: str, task_name: str) -> bool:
    """
    Release a Redis lock for a user.

    Args:
        user_id: The user's ID
        task_name: Name of the task

    Returns:
        bool: True if lock released, False if error
    """
    redis_client = get_redis_client()
    lock_key = f"user_lock:{user_id}:{task_name}"

    try:
        redis_client.delete(lock_key)
    except (redis.RedisError, ConnectionError) as e:
        logger.error(f"Error releasing lock for user {user_id}: {e}")
        return False
    else:
        return True


def is_user_locked(user_id: str, task_name: str) -> bool:
    """
    Check if a user has an active lock for a task.

    Args:
        user_id: The user's ID
        task_name: Name of the task

    Returns:
        bool: True if user is locked, False otherwise
    """
    redis_client = get_redis_client()
    lock_key = f"user_lock:{user_id}:{task_name}"

    try:
        return bool(redis_client.exists(lock_key))
    except (redis.RedisError, ConnectionError) as e:
        logger.error(f"Error checking lock for user {user_id}: {e}")
        return False


@shared_task
def test_celery_task(message: str = "Hello from Celery!") -> str:
    """
    Simple test task to verify Celery is working.

    Args:
        message: Message to return

    Returns:
        str: The message with a timestamp
    """
    logger.info("Test Celery task executed with message: %s", message)
    return f"{message} - Task completed successfully!"


@shared_task
def test_email_task(email_address: str = "test@example.com") -> str:
    """
    Test task to send an email via MailHog for testing.

    Args:
        email_address: Email address to send test email to

    Returns:
        str: Status message
    """
    try:
        email = EmailMessage(
            subject="Test Email from Celery",
            body="This is a test email sent from Celery via MailHog!",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[email_address],
        )
        email.send()
        logger.info("Test email sent successfully to %s", email_address)
    except (OSError, ValueError) as e:
        logger.error("Failed to send test email: %s", e)
        return f"Failed to send email: {e}"
    else:
        return f"Test email sent to {email_address}"


def create_zip_from_files(files: list[File], zip_name: str) -> tuple[str, int, int]:
    """
    Create a zip file from a list of files on disk in a persistent location.

    Args:
        files: List of File model instances to include in the zip
        zip_name: Name for the zip file (default: "download.zip")

    Returns:
        tuple: (zip_file_path, total_size, files_processed)

    Raises:
        OSError: If there's an error creating the zip file
        ValueError: If there's an error processing files
    """
    # Create persistent zip file in media directory
    media_root = Path(settings.MEDIA_ROOT)
    temp_zips_dir = media_root / "temp_zips"
    # Ensure the directory exists
    temp_zips_dir.mkdir(parents=True, exist_ok=True)

    # Create a unique filename to avoid conflicts
    unique_id = str(uuid.uuid4())
    zip_filename = f"{unique_id}_{zip_name}"
    zip_file_path = temp_zips_dir / zip_filename

    total_size = 0
    files_processed = 0

    with zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_obj in files:
            try:
                # Download file content
                file_content = download_file(file_obj)

                # Create a safe filename for the zip
                base_path = sanitize_path_rel_to_user("/", user=file_obj.owner)
                if base_path is not None:
                    # remove the base path from the file_obj.directory
                    rel_path = Path(file_obj.directory).relative_to(base_path)
                    safe_filename = f"{rel_path}/{file_obj.name}"
                else:
                    safe_filename = file_obj.name

                # Add file to zip
                zip_file.writestr(safe_filename, file_content)
                total_size += len(file_content)
                files_processed += 1

                logger.info(
                    "Added file %s to zip (%d bytes)",
                    file_obj.name,
                    len(file_content),
                )

            except (OSError, ValueError):
                logger.exception("Failed to process file %s", file_obj.name)
                # Continue with other files
                continue

    return str(zip_file_path), total_size, files_processed


@shared_task
def cleanup_expired_temp_zips() -> dict:
    """
    Celery task to clean up expired temporary zip files.

    Returns:
        dict: Task result with cleanup statistics
    """
    try:
        # Get expired files that haven't been soft deleted yet
        expired_files = TemporaryZipFile.objects.filter(
            expires_at__lt=datetime.datetime.now(datetime.UTC),
            is_deleted=False,
        )
        count = expired_files.count()

        if count == 0:
            logger.info("No expired temporary zip files to clean up")
            return {
                "status": "success",
                "message": "No expired files found",
                "deleted_count": 0,
                "failed_count": 0,
            }

        logger.info("Cleaning up %d expired temporary zip files", count)

        deleted_count = 0
        failed_count = 0

        for temp_zip in expired_files:
            try:
                # Delete the file from disk
                temp_zip.delete_file()
                deleted_count += 1
                logger.info("Soft deleted expired file: %s", temp_zip.filename)
            except (OSError, ValueError) as e:
                failed_count += 1
                logger.exception("Failed to delete %s: %s", temp_zip.filename, e)

        logger.info(
            "Cleanup complete: %s deleted, %s failed", deleted_count, failed_count
        )

    except (OSError, ValueError) as e:
        logger.exception("Error in cleanup_expired_temp_zips")
        return {
            "status": "error",
            "message": f"Cleanup failed: {e}",
            "deleted_count": 0,
            "failed_count": 0,
        }
    else:
        return {
            "status": "success",
            "message": (
                f"Cleanup complete: {deleted_count} deleted, {failed_count} failed"
            ),
            "deleted_count": deleted_count,
            "failed_count": failed_count,
        }


def get_user_task_status(user_id: str, task_name: str) -> dict:
    """
    Get detailed status information about a user's task.

    Args:
        user_id: The user's ID
        task_name: Name of the task

    Returns:
        dict: Status information including lock status and timestamp
    """
    redis_client = get_redis_client()
    lock_key = f"user_lock:{user_id}:{task_name}"

    try:
        if redis_client.exists(lock_key):
            lock_timestamp = redis_client.get(lock_key)
            ttl = redis_client.ttl(lock_key)

            # Handle potential None values
            timestamp_str = None
            if lock_timestamp:
                try:
                    timestamp_str = lock_timestamp.decode("utf-8")
                except (AttributeError, UnicodeDecodeError):
                    timestamp_str = str(lock_timestamp)

            ttl_value = 0
            if ttl is not None:
                try:
                    ttl_value = max(0, int(ttl))
                except (ValueError, TypeError):
                    ttl_value = 0

            return {
                "is_locked": True,
                "lock_timestamp": timestamp_str,
                "ttl_seconds": ttl_value,
                "task_name": task_name,
                "user_id": user_id,
            }

        return {  # noqa: TRY300
            "is_locked": False,
            "lock_timestamp": None,
            "ttl_seconds": 0,
            "task_name": task_name,
            "user_id": user_id,
        }
    except (redis.RedisError, ConnectionError) as e:
        logger.error(f"Error getting task status for user {user_id}: {e}")
        return {
            "is_locked": False,
            "lock_timestamp": None,
            "ttl_seconds": 0,
            "task_name": task_name,
            "user_id": user_id,
        }


@shared_task
def notify_shared_users(
    item_uuid: str,
    item_type: ItemType,
    user_emails: list[str],
    *,
    notify: bool = True,
    message: str | None = None,
):
    """
    Celery task to notify users when an item is shared with them.
    Args:
        item_uuid: UUID of the shared item
        item_type: Type of item (e.g., "dataset", "capture")
        user_emails: List of user emails to notify
        notify: Whether to send notification emails
        message: Optional custom message to include
    """
    if not notify or not user_emails:
        return "No notifications sent."

    # Map item types to their corresponding models
    item_models = {
        "dataset": Dataset,
        "capture": Capture,
    }

    if item_type not in item_models:
        return f"Invalid item type: {item_type}"

    model_class = item_models[item_type]

    try:
        item = model_class.objects.get(uuid=item_uuid)
        item_name = getattr(item, "name", str(item))
        owner = getattr(item, "owner", None)
        owner_name = getattr(owner, "name", "The owner") if owner else "The owner"
        owner_email = getattr(owner, "email", "") if owner else ""
    except model_class.DoesNotExist:
        return f"{item_type.capitalize()} {item_uuid} does not exist."

    subject = f"A {item_type} has been shared with you: {item_name}"

    # Build item_url if possible
    # Try to provide a direct link to the item list page
    if item_type == "dataset":
        item_url = f"{settings.SITE_URL}/users/dataset-list/"
    elif item_type == "capture":
        item_url = f"{settings.SITE_URL}/users/file-list/"
    else:
        item_url = settings.SITE_URL

    for email in user_emails:
        context = {
            "item_type": item_type,
            "item_name": item_name,
            "owner_name": owner_name,
            "owner_email": owner_email,
            "message": message,
            "item_url": item_url,
            "site_url": settings.SITE_URL,
        }
        if message:
            body = (
                f"You have been granted access to the {item_type} '{item_name}'.\n\n"
                f"Message from the owner:\n{message}\n\n"
                f"View your shared {item_type}s: {item_url}"
            )
        else:
            body = (
                f"You have been granted access to the {item_type} '{item_name}'.\n\n"
                f"View your shared {item_type}s: {item_url}"
            )

        send_email(
            subject=subject,
            recipient_list=[email],
            plain_message=body,
            html_template="emails/share_notification.html",
            context=context,
        )

    return f"Notified {len(user_emails)} users about shared {item_type} {item_uuid}."


def _create_error_response(
    status: str,
    message: str,
    item_uuid: str,
    user_id: str | None = None,
    total_size: int = 0,
) -> dict:
    """Create a standardized error response."""
    response = {
        "status": status,
        "message": message,
        "item_uuid": item_uuid,
    }
    if user_id is not None:
        response["user_id"] = user_id
    if total_size > 0:
        response["total_size"] = total_size
    return response


def _process_item_files(
    user: User, item: Any, item_type: ItemType, item_uuid: str
) -> tuple[dict | None, str | None, int | None, int | None]:
    """
    Process files for an item and create a zip file.

    Returns:
        tuple: (error_response, zip_file_path, total_size, files_processed)
        If error_response is not None, the other values are None
    """
    files = _get_item_files(user, item, item_type)
    if not files:
        logger.warning("No files found for %s %s", item_type, item_uuid)
        error_message = f"No files found in {item_type}"
        _send_item_download_error_email(user, item, item_type, error_message)
        return (
            _create_error_response("error", error_message, item_uuid, total_size=0),
            None,
            None,
            None,
        )

    safe_item_name = (getattr(item, "name", str(item)) or item_type).replace(" ", "_")
    zip_filename = f"{item_type}_{safe_item_name}_{item_uuid}.zip"
    zip_file_path, total_size, files_processed = create_zip_from_files(
        files, zip_filename
    )

    if files_processed == 0:
        logger.warning("No files were processed for %s %s", item_type, item_uuid)
        error_message = "No files could be processed"
        _send_item_download_error_email(user, item, item_type, error_message)
        return (
            _create_error_response("error", error_message, item_uuid, total_size=0),
            None,
            None,
            None,
        )

    return None, zip_file_path, total_size, files_processed


@shared_task
def send_item_files_email(item_uuid: str, user_id: str, item_type: ItemType) -> dict:
    """
    Unified Celery task to create a zip file of item files and send it via email.

    This task handles both datasets and captures using the same logic.

    Args:
        item_uuid: UUID of the item to process
        user_id: ID of the user requesting the download
        item_type: Type of item (dataset or capture)

    Returns:
        dict: Task result with status and details
    """
    # Initialize variables that might be used in finally block
    task_name = f"{item_type}_download"
    user = None
    item = None

    try:
        # Validate the request
        error_result, user, item = _validate_item_download_request(
            item_uuid, user_id, item_type
        )
        if error_result:
            return error_result

        # At this point, user and item are guaranteed to be not None
        assert user is not None
        assert item is not None

        # Check user lock status and acquire lock
        if is_user_locked(user_id, task_name):
            logger.warning(
                "User %s already has a %s download task running", user_id, item_type
            )
            error_message = (
                f"You already have a {item_type} download in progress. "
                "Please wait for it to complete."
            )
            _send_item_download_error_email(user, item, item_type, error_message)
            return _create_error_response("error", error_message, item_uuid, user_id)

        if not acquire_user_lock(user_id, task_name):
            logger.warning("Failed to acquire lock for user %s", user_id)
            error_message = "Unable to start download. Please try again in a moment."
            _send_item_download_error_email(user, item, item_type, error_message)
            return _create_error_response("error", error_message, item_uuid, user_id)

        logger.info(
            "Acquired lock for user %s, starting %s download", user_id, item_type
        )

        # Process files and create zip
        error_response, zip_file_path, total_size, files_processed = (
            _process_item_files(user, item, item_type, item_uuid)
        )
        if error_response:
            return error_response

        # Create temporary zip file record
        safe_item_name = (getattr(item, "name", str(item)) or item_type).replace(
            " ", "_"
        )
        zip_filename = f"{item_type}_{safe_item_name}_{item_uuid}.zip"

        temp_zip = TemporaryZipFile.objects.create(
            file_path=zip_file_path,
            filename=zip_filename,
            file_size=total_size,
            files_processed=files_processed,
            owner=user,
        )

        # Send email with download link
        item_display_name = (
            getattr(item, "name", str(item)) or f"{item_type.capitalize()} {item_uuid}"
        )
        subject = f"Your {item_type} '{item_display_name}' is ready for download"

        # Create email context
        context = {
            "item_type": item_type,
            "item_name": item_display_name,
            "download_url": temp_zip.download_url,
            "file_size": total_size,
            "files_count": files_processed,
            "expires_at": temp_zip.expires_at,
            "site_url": settings.SITE_URL,
        }

        # Send email using the unified template
        send_email(
            subject=subject,
            recipient_list=[user.email],
            html_template="emails/item_download_ready.html",
            plain_template="emails/item_download_ready.txt",
            context=context,
        )

        logger.info(
            "Successfully sent %s download email for %s to %s",
            item_type,
            item_uuid,
            user.email,
        )

        return {
            "status": "success",
            "message": f"{item_type.capitalize()} files email sent successfully",
            "item_uuid": item_uuid,
            "files_processed": files_processed,
            "temp_zip_uuid": temp_zip.uuid,
        }

    except (OSError, ValueError, RuntimeError) as e:
        logger.exception(
            "Error processing %s download for %s: %s",
            item_type,
            item_uuid,
            e,
        )
        # Send error email if we have user and item
        error_message = f"Error processing {item_type} download: {e!s}"
        if user is not None and item is not None:
            _send_item_download_error_email(user, item, item_type, error_message)
        return _create_error_response("error", error_message, item_uuid)

    finally:
        # Always release the lock, even if there was an error
        if user_id is not None:
            release_user_lock(user_id, task_name)
            logger.info("Released lock for user %s", user_id)


def _validate_item_download_request(
    item_uuid: str, user_id: str, item_type: ItemType
) -> tuple[dict | None, User | None, Any]:
    """
    Validate item download request parameters.

    Args:
        item_uuid: UUID of the item to download
        user_id: ID of the user requesting the download
        item_type: Type of item (dataset or capture)

    Returns:
        tuple: (error_result, user, item) where error_result is None if valid
    """
    # Map item types to their corresponding models
    item_models = {
        ItemType.DATASET: Dataset,
        ItemType.CAPTURE: Capture,
    }

    if item_type not in item_models:
        return (
            {
                "status": "error",
                "message": f"Invalid item type: {item_type}",
                "item_uuid": item_uuid,
                "user_id": user_id,
            },
            None,
            None,
        )

    model_class = item_models[item_type]

    # Validate user
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.warning("User %s not found for %s download", user_id, item_type)
        return (
            {
                "status": "error",
                "message": "User not found",
                "item_uuid": item_uuid,
                "user_id": user_id,
            },
            None,
            None,
        )

    # Validate item access (either as owner or shared user)
    if not user_has_access_to_item(user, item_uuid, item_type):
        logger.warning(
            "%s %s not found or access denied for user %s",
            item_type.capitalize(),
            item_uuid,
            user_id,
        )
        return (
            {
                "status": "error",
                "message": f"{item_type.capitalize()} not found or access denied",
                "item_uuid": item_uuid,
                "user_id": user_id,
            },
            None,
            None,
        )

    # Get the item
    try:
        item = model_class.objects.get(
            uuid=item_uuid,
            is_deleted=False,
        )
    except model_class.DoesNotExist:
        logger.warning(
            "%s %s not found",
            item_type.capitalize(),
            item_uuid,
        )
        return (
            {
                "status": "error",
                "message": f"{item_type.capitalize()} not found",
                "item_uuid": item_uuid,
                "user_id": user_id,
            },
            None,
            None,
        )

    return None, user, item


def _get_item_files(user: User, item: Any, item_type: ItemType) -> list[File]:
    """
    Get all files for an item based on its type.

    Args:
        user: The user requesting the files
        item: The item object (Dataset or Capture)
        item_type: Type of item (dataset or capture)

    Returns:
        List of files associated with the item
    """
    if item_type == ItemType.DATASET:
        # Get all files directly associated with the dataset
        files = item.files.filter(
            is_deleted=False,
        )
        # Get all captures associated with the dataset
        captures = item.captures.filter(
            is_deleted=False,
        )
        # Get all files from those captures
        capture_files = File.objects.filter(
            capture__in=captures,
            is_deleted=False,
        )
        return list(files) + list(capture_files)

    if item_type == ItemType.CAPTURE:
        # Get all files for the capture
        return list(item.files.filter(is_deleted=False))

    logger.warning("Unknown item type: %s", item_type)
    return []


def _send_item_download_error_email(
    user: User, item: Any, item_type: ItemType, error_message: str
) -> None:
    """
    Send error email for item download failures.

    Args:
        user: The user who requested the download
        item: The item that failed to download
        item_type: Type of item (dataset or capture)
        error_message: The error message to include
    """
    try:
        item_name = getattr(item, "name", str(item))
        subject = f"Error downloading your {item_type}: {item_name}"

        context = {
            "item_type": item_type,
            "item_name": item_name,
            "error_message": error_message,
            "requested_at": datetime.datetime.now(datetime.UTC).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            ),
            "site_url": settings.SITE_URL,
        }

        send_email(
            subject=subject,
            recipient_list=[user.email],
            plain_template="emails/item_download_error.txt",
            html_template="emails/item_download_error.html",
            context=context,
        )

        logger.info(
            "Sent error email for %s %s to %s: %s",
            item_type,
            item.uuid,
            user.email,
            error_message,
        )

    except (OSError, ValueError) as e:
        logger.exception(
            "Failed to send error email for %s %s to user %s: %s",
            item_type,
            item.uuid,
            user.id,
            e,
        )
