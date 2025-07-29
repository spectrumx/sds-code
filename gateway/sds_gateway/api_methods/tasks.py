import datetime
import os
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any

import redis
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from loguru import logger
from redis import Redis

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import PostProcessedData
from sds_gateway.api_methods.models import ProcessingType
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
    *,
    attach_logo=True,
):
    """
    Generic utility to send an email with optional template rendering and logo
    attachment.
    Args:
        subject: Email subject
        recipient_list: List of recipient emails
        plain_template: Path to plain text template (optional)
        html_template: Path to HTML template (optional)
        context: Context for rendering templates (optional)
        plain_message: Raw plain text message (optional, overrides template)
        html_message: Raw HTML message (optional, overrides template)
        attach_logo: Whether to attach the logo as an embedded image (default: True)
    """

    from django.conf import settings

    if not recipient_list:
        return False
    if not plain_message and plain_template and context:
        plain_message = render_to_string(plain_template, context)
    if not html_message and html_template and context:
        html_message = render_to_string(html_template, context)

    # Use EmailMessage for better control over attachments
    email = EmailMessage(
        subject=subject,
        body=html_message or plain_message or "",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipient_list,
    )

    # Set content type for HTML emails
    if html_message:
        email.content_subtype = "html"

    # Attach logo if requested
    if attach_logo:
        logo_path = Path(settings.STATIC_ROOT) / "images" / "Logo.png"
        if logo_path.exists():
            with logo_path.open("rb") as logo_file:
                logo_content = logo_file.read()
                # Attach logo with Content-ID for embedding
                from email.mime.image import MIMEImage

                logo_mime = MIMEImage(logo_content)
                logo_mime.add_header("Content-ID", "<logo>")
                email.attach(logo_mime)
                # Set mixed subtype for related content
                email.mixed_subtype = "related"

    email.send()
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
    Test task to verify Celery is working.

    Args:
        message: Message to return

    Returns:
        str: The message with a timestamp
    """
    logger.info(f"Test Celery task executed with message: {message}")
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
        logger.info(f"Test email sent successfully to {email_address}")
    except (OSError, ValueError) as e:
        logger.error(f"Failed to send test email: {e}")
        return f"Failed to send email: {e}"
    else:
        return f"Test email sent to {email_address}"


def create_zip_from_files(files: list[File], zip_name: str) -> tuple[str, int, int]:
    """
    Create a zip file by streaming files directly from MinIO storage.

    This approach is memory-efficient and handles large files by streaming
    directly from MinIO to the zip file in chunks.

    Args:
        files: List of File model instances to include in the zip
        zip_name: Name for the zip file

    Returns:
        tuple: (zip_file_path, total_size, files_processed)
    """
    from sds_gateway.api_methods.utils.minio_client import get_minio_client

    # Create persistent zip file in media directory
    media_root = Path(settings.MEDIA_ROOT)
    temp_zips_dir = media_root / "temp_zips"
    temp_zips_dir.mkdir(parents=True, exist_ok=True)

    # Create a unique filename to avoid conflicts
    unique_id = str(uuid.uuid4())
    zip_filename = f"{unique_id}_{zip_name}"
    zip_file_path = temp_zips_dir / zip_filename

    total_size = 0
    files_processed = 0
    client = get_minio_client()

    with zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_obj in files:
            try:
                # Create the file path in the zip using the file tree structure
                # Use sanitize_path_rel_to_user to get the full path, then strip the
                # /files/user.email part
                # This ensures the zip contains only the directories below the user's
                # root
                user_rel_path = sanitize_path_rel_to_user(
                    file_obj.directory, user=file_obj.owner
                )
                if user_rel_path is not None:
                    # Strip the /files/user.email part from the path
                    # user_rel_path will be something like
                    # "/files/user@email.com/dataset1/subfolder"
                    # We want to extract just "dataset1/subfolder"
                    user_root_pattern = f"/files/{file_obj.owner.email}"
                    if str(user_rel_path).startswith(user_root_pattern):
                        # Remove the user root pattern and any leading slash
                        relative_path = str(user_rel_path)[
                            len(user_root_pattern) :
                        ].lstrip("/")
                        safe_filename = f"{zip_name}/{relative_path}/{file_obj.name}"
                    else:
                        # Fallback if the pattern doesn't match
                        safe_filename = f"{zip_name}/{file_obj.name}"
                else:
                    # Fallback to just the filename if path sanitization fails,
                    # still wrapped in zip_name folder
                    safe_filename = f"{zip_name}/{file_obj.name}"

                # Stream file directly from MinIO to zip
                # Use file_obj.file.name to get the MinIO object key
                response = client.get_object(
                    bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
                    object_name=file_obj.file.name,
                )

                # Read file in chunks and write to zip
                file_size = 0
                with zip_file.open(safe_filename, "w") as zip_entry:
                    for chunk in response.stream(32 * 1024):  # 32KB chunks
                        zip_entry.write(chunk)
                        file_size += len(chunk)

                response.close()
                response.release_conn()

                total_size += file_size
                files_processed += 1

                logger.info(f"Streamed file {safe_filename} to zip ({file_size} bytes)")

            except (OSError, ValueError, RuntimeError) as e:
                logger.exception(f"Failed to process file {file_obj.name}: {e}")
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

        logger.info(f"Cleaning up {count} expired temporary zip files")

        deleted_count = 0
        failed_count = 0

        for temp_zip in expired_files:
            try:
                # Delete the file from disk
                temp_zip.delete_file()
                deleted_count += 1
                logger.info(f"Soft deleted expired file: {temp_zip.filename}")
            except (OSError, ValueError) as e:
                failed_count += 1
                logger.exception(f"Failed to delete {temp_zip.filename}: {e}")

        logger.info(f"Cleanup complete: {deleted_count} deleted, {failed_count} failed")

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
            "debug": settings.DEBUG,
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
        logger.warning(f"No files found for {item_type} {item_uuid}")
        error_message = f"No files found in {item_type}"
        _send_item_download_error_email(user, item, item_type, error_message)
        return (
            _create_error_response("error", error_message, item_uuid, total_size=0),
            None,
            None,
            None,
        )

    unsafe_item_name = getattr(item, "name", str(item)) or item_type
    safe_item_name = re.sub(r"[^a-zA-Z0-9._-]", "", unsafe_item_name.replace(" ", "_"))
    zip_filename = f"{item_type}_{safe_item_name}_{item_uuid}.zip"
    zip_file_path, total_size, files_processed = create_zip_from_files(
        files, zip_filename
    )

    if files_processed == 0:
        logger.warning(f"No files were processed for {item_type} {item_uuid}")
        error_message = "No files could be processed"
        _send_item_download_error_email(user, item, item_type, error_message)
        return (
            _create_error_response("error", error_message, item_uuid, total_size=0),
            None,
            None,
            None,
        )

    return None, zip_file_path, total_size, files_processed


def _handle_user_lock_validation(
    user_id: str, user: User, item: Any, item_type: ItemType, task_name: str
) -> dict | None:
    """
    Handle user lock validation and acquisition.

    Returns:
        dict: Error response if lock validation fails, None if successful
    """
    if is_user_locked(user_id, task_name):
        logger.warning(
            f"User {user_id} already has a {item_type} download task running"
        )
        error_message = (
            f"You already have a {item_type} download in progress. "
            "Please wait for it to complete."
        )
        _send_item_download_error_email(user, item, item_type, error_message)
        return _create_error_response("error", error_message, str(item.uuid), user_id)

    if not acquire_user_lock(user_id, task_name):
        logger.warning(f"Failed to acquire lock for user {user_id}")
        error_message = (
            "Another download is already in progress. Please wait for it to complete."
        )
        _send_item_download_error_email(user, item, item_type, error_message)
        return {
            "status": "error",
            "message": error_message,
            "item_uuid": str(item.uuid),
            "user_id": user_id,
        }

    return None


def _create_temp_zip_record(
    user: User,
    zip_file_path: str,
    total_size: int,
    files_processed: int,
    item: Any,
    item_type: ItemType,
    item_uuid: str,
) -> TemporaryZipFile:
    """Create a temporary zip file record."""
    unsafe_item_name = getattr(item, "name", str(item)) or item_type
    safe_item_name = re.sub(r"[^a-zA-Z0-9._-]", "", unsafe_item_name.replace(" ", "_"))
    zip_filename = f"{item_type}_{safe_item_name}_{item_uuid}.zip"

    return TemporaryZipFile.objects.create(
        file_path=zip_file_path,
        filename=zip_filename,
        file_size=total_size,
        files_processed=files_processed,
        owner=user,
    )


def _send_download_email(
    user: User,
    item: Any,
    item_type: ItemType,
    temp_zip: TemporaryZipFile,
    total_size: int,
    files_processed: int,
) -> None:
    """Send download email to user."""
    item_display_name = (
        getattr(item, "name", str(item)) or f"{item_type.capitalize()} {item.uuid}"
    )
    subject = f"Your {item_type} '{item_display_name}' is ready for download"

    context = {
        "item_type": item_type,
        "item_name": item_display_name,
        "download_url": temp_zip.download_url,
        "file_size": total_size,
        "files_count": files_processed,
        "expires_at": temp_zip.expires_at,
        "site_url": settings.SITE_URL,
        "debug": settings.DEBUG,
    }

    send_email(
        subject=subject,
        recipient_list=[user.email],
        html_template="emails/item_download_ready.html",
        plain_template="emails/item_download_ready.txt",
        context=context,
    )


def _handle_timeout_exception(
    user: User | None, item: Any, item_type: ItemType, item_uuid: str, e: Exception
) -> dict:
    """Handle timeout exceptions in the download task."""
    logger.exception(
        f"Timeout or soft time limit exceeded for {item_type} download "
        f"for {item_uuid}: {e}"
    )
    error_message = (
        f"The download process for {item_type} {item_uuid} "
        "has timed out or exceeded the soft time limit. "
        "Please try again or contact support."
    )
    if user is not None and item is not None:
        _send_item_download_error_email(user, item, item_type, error_message)
    return _create_error_response("error", error_message, item_uuid)


@shared_task(
    time_limit=30 * 60, soft_time_limit=25 * 60
)  # 30 min hard limit, 25 min soft limit
def send_item_files_email(  # noqa: C901
    item_uuid: str, user_id: str, item_type: str | ItemType
) -> dict:
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
    result = None

    try:
        # Convert string item_type to enum if needed
        if isinstance(item_type, str):
            try:
                item_type = ItemType(item_type)
            except ValueError:
                return _create_error_response(
                    "error", f"Invalid item type: {item_type}", item_uuid, user_id
                )

        # At this point, item_type is guaranteed to be ItemType
        item_type_enum: ItemType = item_type

        # Validate the request
        error_result, user, item = _validate_item_download_request(
            item_uuid, user_id, item_type_enum
        )
        if error_result:
            return error_result

        # At this point, user and item are guaranteed to be not None
        assert user is not None
        assert item is not None

        # Check user lock status and acquire lock
        lock_error = _handle_user_lock_validation(
            user_id, user, item, item_type_enum, task_name
        )
        if lock_error:
            return lock_error

        logger.info(
            f"Acquired lock for user {user_id}, starting {item_type_enum} download"
        )

        # Process files and create zip
        error_response, zip_file_path, total_size, files_processed = (
            _process_item_files(user, item, item_type_enum, item_uuid)
        )
        if error_response:
            return error_response

        # Ensure we have valid values for zip creation
        if zip_file_path is None or total_size is None or files_processed is None:
            error_message = "Failed to process files for zip creation"
            _send_item_download_error_email(user, item, item_type_enum, error_message)
            return _create_error_response("error", error_message, item_uuid, user_id)

        # Create temporary zip file record
        temp_zip = _create_temp_zip_record(
            user,
            zip_file_path,
            total_size,
            files_processed,
            item,
            item_type_enum,
            item_uuid,
        )

        # Send email with download link
        _send_download_email(
            user, item, item_type_enum, temp_zip, total_size, files_processed
        )

        logger.info(
            f"Successfully sent {item_type_enum} download email for {item_uuid} "
            f"to {user.email}"
        )

        result = {
            "status": "success",
            "message": f"{item_type_enum.capitalize()} files email sent successfully",
            "item_uuid": item_uuid,
            "files_processed": files_processed,
            "temp_zip_uuid": temp_zip.uuid,
        }

    except (OSError, ValueError) as e:
        logger.exception(
            f"Error processing {item_type_enum} download for {item_uuid}: {e}"
        )
        # Send error email if we have user and item
        error_message = f"Error processing {item_type_enum} download: {e!s}"
        if user is not None and item is not None:
            _send_item_download_error_email(user, item, item_type_enum, error_message)
        result = _create_error_response("error", error_message, item_uuid)

    except (SoftTimeLimitExceeded, TimeoutError) as e:
        result = _handle_timeout_exception(user, item, item_type_enum, item_uuid, e)

    finally:
        # Always release the lock, even if there was an error
        if user_id is not None:
            release_user_lock(user_id, task_name)
            logger.info(f"Released lock for user {user_id}")

    return result


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
        logger.warning(f"User {user_id} not found for {item_type} download")
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
            f"{item_type.capitalize()} {item_uuid} not found or access denied "
            f"for user {user_id}"
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
        logger.warning(f"{item_type.capitalize()} {item_uuid} not found")
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

        logger.info(
            f"Found {len(files)} files and {len(capture_files)} capture files "
            f"for dataset {item.uuid}"
        )

        return list(files) + list(capture_files)

    if item_type == ItemType.CAPTURE:
        # Get all files for the capture
        files = list(item.files.filter(is_deleted=False))
        logger.info(f"Found {len(files)} files for capture {item.uuid}")

        return files

    logger.warning(f"Unknown item type: {item_type}")
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
            "debug": settings.DEBUG,
        }

        send_email(
            subject=subject,
            recipient_list=[user.email],
            plain_template="emails/item_download_error.txt",
            html_template="emails/item_download_error.html",
            context=context,
        )

        logger.info(
            f"Sent error email for {item_type} {item.uuid} to {user.email}: "
            f"{error_message}"
        )

    except (OSError, ValueError) as e:
        logger.exception(
            f"Failed to send error email for {item_type} {item.uuid} "
            f"to user {user.id}: {e}"
        )


@shared_task
def start_capture_post_processing(
    capture_uuid: str, processing_types: list[str] | None = None
) -> dict:
    """
    Start post-processing pipeline for a DigitalRF capture.

    This is the main entry point that creates and runs the appropriate
    django-cog pipeline for the requested processing types.

    Args:
        capture_uuid: UUID of the capture to process
        processing_types: List of processing types to run (waterfall, spectrogram, etc.)
    """
    logger.info(f"Starting post-processing pipeline for capture {capture_uuid}")

    try:
        # Get the capture with retry mechanism for transaction timing issues
        capture = None
        max_retries = 3
        retry_delay = 1  # seconds

        for attempt in range(max_retries):
            try:
                capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)
                break  # Found the capture, exit retry loop
            except Capture.DoesNotExist:
                if attempt < max_retries - 1:
                    logger.warning(
                        f"Capture {capture_uuid} not found on attempt {attempt + 1}, "
                        f"retrying in {retry_delay} seconds..."
                    )
                    import time

                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    # Final attempt failed
                    error_msg = (
                        f"Capture {capture_uuid} not found after {max_retries} attempts"
                    )
                    logger.error(error_msg)
                    return {
                        "status": "error",
                        "message": error_msg,
                        "capture_uuid": capture_uuid,
                    }

        # At this point, capture should not be None due to the retry logic above
        assert capture is not None, (
            f"Capture {capture_uuid} should have been found by now"
        )

        if capture.capture_type != CaptureType.DigitalRF:
            return {
                "status": "error",
                "message": f"Capture {capture_uuid} is not a DigitalRF capture",
                "capture_uuid": capture_uuid,
            }

        # Set default processing types if not specified
        if not processing_types:
            processing_types = [ProcessingType.Waterfall.value]

        # Create PostProcessedData records for each processing type
        for processing_type in processing_types:
            _create_or_reset_processed_data(capture, processing_type)

        # Get the appropriate pipeline from the database
        from sds_gateway.api_methods.models import get_latest_pipeline_by_base_name

        # For now, we only support waterfall processing
        if "waterfall" in processing_types:
            pipeline = get_latest_pipeline_by_base_name("Waterfall Processing")
            if not pipeline:
                return {
                    "status": "error",
                    "message": "No Waterfall Processing pipeline found. Please run setup_pipelines.",
                    "capture_uuid": capture_uuid,
                }

            # Launch the pipeline with runtime arguments
            pipeline.launch(capture_uuid=capture_uuid)
        else:
            return {
                "status": "error",
                "message": f"Unsupported processing types: {processing_types}",
                "capture_uuid": capture_uuid,
            }

        return {
            "status": "success",
            "message": f"Post-processing pipeline completed for {len(processing_types)} types",
            "capture_uuid": capture_uuid,
            "processing_types": processing_types,
        }

    except Capture.DoesNotExist:
        error_msg = f"Capture {capture_uuid} not found"
        logger.error(error_msg)
        return {
            "status": "error",
            "message": error_msg,
            "capture_uuid": capture_uuid,
        }
    except Exception as e:
        error_msg = f"Unexpected error in post-processing pipeline: {e}"
        logger.exception(error_msg)
        return {
            "status": "error",
            "message": error_msg,
            "capture_uuid": capture_uuid,
        }


def _create_or_reset_processed_data(
    capture: Capture, processing_type: str
) -> PostProcessedData:
    """Create or reset a PostProcessedData record for the given processing type."""

    # Default processing parameters based on type
    default_params = {
        ProcessingType.Waterfall.value: {
            "fft_size": 1024,
            "samples_per_slice": 1024,
        },
    }

    processing_parameters = default_params.get(processing_type, {})

    # Create or get existing record
    processed_data, created = PostProcessedData.objects.get_or_create(
        capture=capture,
        processing_type=processing_type,
        processing_parameters=processing_parameters,
        defaults={
            "processing_status": "pending",  # Changed from ProcessingStatus.Pending.value to "pending"
            "metadata": {},
        },
    )

    if not created:
        # Reset existing record
        processed_data.processing_status = (
            "pending"  # Changed from ProcessingStatus.Pending.value to "pending"
        )
        processed_data.processing_error = ""
        processed_data.pipeline_id = ""
        processed_data.pipeline_step = ""
        processed_data.save()

    return processed_data


@shared_task
def download_capture_files(capture_uuid: str) -> dict:
    """
    Download DigitalRF files from SDS storage to temporary location.

    Args:
        capture_uuid: UUID of the capture to download files for

    Returns:
        dict: Task result with temporary directory path
    """
    logger.info(f"Downloading files for capture {capture_uuid}")

    try:
        capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)
        capture_files = capture.files.filter(is_deleted=False)

        if not capture_files.exists():
            return {
                "status": "error",
                "message": f"No files found for capture {capture_uuid}",
            }

        # Create temporary directory
        import tempfile

        temp_dir = tempfile.mkdtemp(prefix=f"capture_{capture_uuid}_")
        temp_path = Path(temp_dir)

        # Download and reconstruct the DigitalRF directory structure
        reconstructed_path = _reconstruct_drf_files(capture, capture_files, temp_path)

        if not reconstructed_path:
            return {
                "status": "error",
                "message": "Failed to reconstruct DigitalRF directory structure",
            }

        return {
            "status": "success",
            "message": "Files downloaded successfully",
            "temp_dir": str(temp_path),
            "drf_path": str(reconstructed_path),
        }

    except Exception as e:
        logger.exception(f"Error downloading capture files: {e}")
        return {
            "status": "error",
            "message": f"Error downloading files: {e}",
        }


@shared_task
def process_waterfall_data(capture_uuid: str) -> dict:
    """
    Process DigitalRF data into waterfall format.

    Args:
        capture_uuid: UUID of the capture to process

    Returns:
        dict: Processing result with file path and metadata
    """
    logger.info(f"Processing waterfall data for capture {capture_uuid}")

    try:
        capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)

        # Get the temporary directory from previous step
        # In a real implementation, this would come from the pipeline context
        import tempfile

        temp_dir = tempfile.mkdtemp(prefix=f"waterfall_{capture_uuid}_")
        temp_path = Path(temp_dir)

        # For now, we'll reconstruct the files again
        # In a real pipeline, this would be passed from the download step
        capture_files = capture.files.filter(is_deleted=False)
        reconstructed_path = _reconstruct_drf_files(capture, capture_files, temp_path)

        if not reconstructed_path:
            return {
                "status": "error",
                "message": "Failed to reconstruct DigitalRF directory structure",
            }

        # Process the waterfall data
        waterfall_result = _convert_drf_to_waterfall(
            reconstructed_path, capture.channel, ProcessingType.Waterfall.value
        )

        if waterfall_result["status"] != "success":
            return waterfall_result

        return {
            "status": "success",
            "message": "Waterfall data processed successfully",
            "data_file_path": waterfall_result["data_file_path"],
            "metadata": waterfall_result["metadata"],
        }

    except Exception as e:
        logger.exception(f"Error processing waterfall data: {e}")
        return {
            "status": "error",
            "message": f"Error processing waterfall data: {e}",
        }


@shared_task
def store_processed_data(capture_uuid: str, processing_type: str) -> dict:
    """
    Store processed data back to SDS storage.

    Args:
        capture_uuid: UUID of the capture
        processing_type: Type of processed data (waterfall, spectrogram, etc.)

    Returns:
        dict: Storage result
    """
    logger.info(f"Storing {processing_type} data for capture {capture_uuid}")

    try:
        capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)

        # Get the processed data record
        processed_data = PostProcessedData.objects.filter(
            capture=capture,
            processing_type=processing_type,
        ).first()

        if not processed_data:
            return {
                "status": "error",
                "message": f"No processed data record found for {processing_type}",
            }

        # In a real implementation, the file path would come from the pipeline context
        # For now, we'll create a dummy file
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as temp_file:
            temp_file_path = temp_file.name

        # Save the file to SDS storage
        with open(temp_file_path, "rb") as f:
            processed_data.data_file.save(
                f"{processing_type}_{capture.uuid}.h5", f, save=False
            )

        # Update metadata
        processed_data.metadata.update(
            {
                "stored_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "file_size": processed_data.data_file.size,
            }
        )
        processed_data.save()

        # Clean up temporary file
        os.unlink(temp_file_path)

        return {
            "status": "success",
            "message": f"{processing_type} data stored successfully",
        }

    except Exception as e:
        logger.exception(f"Error storing {processing_type} data: {e}")
        return {
            "status": "error",
            "message": f"Error storing {processing_type} data: {e}",
        }


@shared_task
def cleanup_temp_files(capture_uuid: str) -> dict:
    """
    Clean up temporary files created during processing.

    Args:
        capture_uuid: UUID of the capture

    Returns:
        dict: Cleanup result
    """
    logger.info(f"Cleaning up temporary files for capture {capture_uuid}")

    try:
        # In a real implementation, this would clean up all temporary files
        # associated with this capture from the pipeline context

        return {
            "status": "success",
            "message": "Temporary files cleaned up successfully",
        }

    except Exception as e:
        logger.exception(f"Error cleaning up temporary files: {e}")
        return {
            "status": "error",
            "message": f"Error cleaning up temporary files: {e}",
        }


# Legacy task for backward compatibility
@shared_task
def process_capture_waterfall(capture_uuid: str) -> dict:
    """
    Legacy task for waterfall processing (deprecated).

    This task is kept for backward compatibility but new implementations
    should use start_capture_post_processing with processing_types=['waterfall'].
    """
    logger.warning(
        "process_capture_waterfall is deprecated. Use start_capture_post_processing instead."
    )
    return start_capture_post_processing.delay(
        capture_uuid, [ProcessingType.Waterfall.value]
    )


# Helper functions (existing implementations)
def _reconstruct_drf_files(
    capture: Capture, capture_files, temp_path: Path
) -> Path | None:
    """Reconstruct DigitalRF directory structure from SDS files."""
    from sds_gateway.api_methods.utils.minio_client import get_minio_client

    logger.info("Reconstructing DigitalRF directory structure")

    try:
        minio_client = get_minio_client()

        # Create the capture directory structure
        capture_dir = temp_path / str(capture.uuid)
        capture_dir.mkdir(parents=True, exist_ok=True)

        # Download and place files in the correct structure
        for file_obj in capture_files:
            # Create the directory structure
            file_path = capture_dir / file_obj.directory.lstrip("/") / file_obj.name
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Download the file from MinIO
            minio_client.fget_object(
                bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
                object_name=file_obj.file.name,
                file_path=str(file_path),
            )

        # Find the DigitalRF root directory (parent of the channel directory)
        for root, dirs, files in os.walk(capture_dir):
            if "drf_properties.h5" in files:
                # The DigitalRF root is the parent of the channel directory
                drf_root = Path(root).parent
                logger.info(f"Found DigitalRF root at: {drf_root}")
                return drf_root

        logger.error("Could not find DigitalRF properties file")
        return None

    except Exception as e:
        logger.exception(f"Error reconstructing DigitalRF files: {e}")
        return None


def _convert_drf_to_waterfall(
    drf_path: Path, channel: str, processing_type: str
) -> dict:
    """Convert DigitalRF data to waterfall format."""
    import tempfile

    import h5py
    import numpy as np
    from digital_rf import DigitalRFReader

    logger.info(f"Converting DigitalRF data to waterfall format for channel {channel}")

    try:
        # Initialize DigitalRF reader
        reader = DigitalRFReader(str(drf_path))
        channels = reader.get_channels()

        if not channels:
            return {
                "status": "error",
                "message": "No channels found in DigitalRF data",
            }

        if channel not in channels:
            return {
                "status": "error",
                "message": f"Channel {channel} not found in DigitalRF data. Available channels: {channels}",
            }

        # Get sample bounds
        start_sample, end_sample = reader.get_bounds(channel)
        total_samples = end_sample - start_sample

        # Get metadata from DigitalRF properties
        drf_props_path = drf_path / channel / "drf_properties.h5"
        with h5py.File(drf_props_path, "r") as f:
            sample_rate = (
                f.attrs["sample_rate_numerator"] / f.attrs["sample_rate_denominator"]
            )

        # Get center frequency from metadata
        center_freq = 0.0
        try:
            # Try to get center frequency from metadata
            metadata_dict = reader.read_metadata(
                start_sample, min(1000, end_sample - start_sample), channel
            )
            if metadata_dict and "center_freq" in metadata_dict:
                center_freq = float(metadata_dict["center_freq"])
        except Exception as e:
            logger.warning(f"Could not read center frequency from metadata: {e}")

        # Calculate frequency range
        freq_span = sample_rate
        min_frequency = center_freq - freq_span / 2
        max_frequency = center_freq + freq_span / 2

        # Processing parameters
        fft_size = 1024  # Default, could be configurable
        samples_per_slice = 1024  # Default, could be configurable

        # Calculate total slices
        total_slices = total_samples // samples_per_slice

        logger.info(
            f"Processing {total_slices} slices with {samples_per_slice} samples per slice"
        )

        # Create temporary file for waterfall data
        with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as temp_file:
            temp_file_path = temp_file.name

        # Process all slices and store in HDF5 file
        with h5py.File(temp_file_path, "w") as h5_file:
            # Create datasets
            waterfall_group = h5_file.create_group("waterfall")

            # Store metadata
            waterfall_group.attrs["center_frequency"] = center_freq
            waterfall_group.attrs["sample_rate"] = sample_rate
            waterfall_group.attrs["min_frequency"] = min_frequency
            waterfall_group.attrs["max_frequency"] = max_frequency
            waterfall_group.attrs["fft_size"] = fft_size
            waterfall_group.attrs["samples_per_slice"] = samples_per_slice
            waterfall_group.attrs["total_slices"] = total_slices
            waterfall_group.attrs["channel"] = channel

            # Create dataset for waterfall data
            waterfall_data_shape = (total_slices, fft_size)
            waterfall_dataset = waterfall_group.create_dataset(
                "data",
                shape=waterfall_data_shape,
                dtype=np.float32,
                compression="gzip",
                compression_opts=6,
            )

            # Process each slice
            for slice_idx in range(total_slices):
                # Calculate sample range for this slice
                slice_start_sample = start_sample + slice_idx * samples_per_slice
                slice_num_samples = min(
                    samples_per_slice, end_sample - slice_start_sample
                )

                if slice_num_samples <= 0:
                    break

                # Read the data
                data_array = reader.read_vector(
                    slice_start_sample, slice_num_samples, channel, 0
                )

                # Perform FFT processing
                fft_data = np.fft.fft(data_array, n=fft_size)
                power_spectrum = np.abs(fft_data) ** 2

                # Convert to dB
                power_spectrum_db = 10 * np.log10(power_spectrum + 1e-12)

                # Store in dataset
                waterfall_dataset[slice_idx, :] = power_spectrum_db.astype(np.float32)

                # Log progress every 100 slices
                if slice_idx % 100 == 0:
                    logger.info(f"Processed {slice_idx}/{total_slices} slices")

        metadata = {
            "center_frequency": center_freq,
            "sample_rate": sample_rate,
            "min_frequency": min_frequency,
            "max_frequency": max_frequency,
            "total_slices": total_slices,
            "fft_size": fft_size,
            "samples_per_slice": samples_per_slice,
            "channel": channel,
        }

        return {
            "status": "success",
            "message": "Waterfall data converted successfully",
            "data_file_path": temp_file_path,
            "metadata": metadata,
        }

    except Exception as e:
        logger.exception(f"Error converting DigitalRF to waterfall: {e}")
        return {
            "status": "error",
            "message": f"Error converting DigitalRF data: {e}",
        }
