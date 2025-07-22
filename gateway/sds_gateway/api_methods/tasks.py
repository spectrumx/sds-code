import datetime
import os
import uuid
import zipfile
from pathlib import Path

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
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import PostProcessedData
from sds_gateway.api_methods.models import ProcessingType
from sds_gateway.api_methods.models import TemporaryZipFile
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


def _send_download_error_email(
    user: User, dataset: Dataset, error_message: str
) -> None:
    """
    Send an error email to the user when dataset download fails.

    Args:
        user: The user to send the email to
        dataset: The dataset that failed to download
        error_message: The error message to include in the email
    """
    try:
        subject = f"Dataset download failed: {dataset.name}"

        # Create email context
        context = {
            "dataset_name": dataset.name,
            "site_url": settings.SITE_URL,
            "error_message": error_message,
            "requested_at": datetime.datetime.now(datetime.UTC).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            ),
        }

        send_email(
            subject=subject,
            recipient_list=[user.email],
            plain_template="emails/dataset_download_error.txt",
            html_template="emails/dataset_download_error.html",
            context=context,
        )

        logger.info(
            "Sent error email for dataset %s to %s: %s",
            dataset.uuid,
            user.email,
            error_message,
        )

    except (OSError, ValueError) as e:
        logger.exception(
            "Failed to send error email for dataset %s to user %s: %s",
            dataset.uuid,
            user.id,
            e,
        )


def _validate_dataset_download_request(
    dataset_uuid: str, user_id: str
) -> tuple[dict | None, User | None, Dataset | None]:
    """
    Validate the dataset download request.

    Returns:
        tuple: (error_result, user, dataset) - error_result is None if validation passes
    """
    # Get the user
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error("User %s not found", user_id)
        return (
            {
                "status": "error",
                "message": "User not found",
                "dataset_uuid": dataset_uuid,
            },
            None,
            None,
        )

    # Get the dataset - allow both owners and shared users to download
    try:
        dataset = Dataset.objects.get(
            uuid=dataset_uuid,
            is_deleted=False,
        )
    except Dataset.DoesNotExist:
        logger.warning(
            "Dataset %s not found",
            dataset_uuid,
        )
        return (
            {
                "status": "error",
                "message": "Dataset not found",
                "dataset_uuid": dataset_uuid,
            },
            None,
            None,
        )

    # Check if user is owner or shared user
    is_owner = dataset.owner == user
    is_shared_user = user in dataset.shared_with.all()

    if not (is_owner or is_shared_user):
        logger.warning(
            "User %s does not have permission to download dataset %s",
            user_id,
            dataset_uuid,
        )
        return (
            {
                "status": "error",
                "message": "You don't have permission to download this dataset",
                "dataset_uuid": dataset_uuid,
            },
            None,
            None,
        )

    return None, user, dataset


def _check_user_lock(
    user_id: str, task_name: str, user: User, dataset: Dataset
) -> dict | None:
    """Check if user is locked and return error if so."""
    if is_user_locked(user_id, task_name):
        logger.warning("User %s already has a dataset download task running", user_id)
        error_message = (
            "You already have a dataset download in progress. "
            "Please wait for it to complete."
        )
        _send_download_error_email(user, dataset, error_message)
        return {
            "status": "error",
            "message": error_message,
            "dataset_uuid": dataset.uuid,
            "user_id": user_id,
        }
    return None


def _acquire_user_lock(
    user_id: str, task_name: str, user: User, dataset: Dataset
) -> dict | None:
    """Try to acquire lock for user and return error if failed."""
    if not acquire_user_lock(user_id, task_name):
        logger.warning("Failed to acquire lock for user %s", user_id)
        error_message = "Unable to start download. Please try again in a moment."
        _send_download_error_email(user, dataset, error_message)
        return {
            "status": "error",
            "message": error_message,
            "dataset_uuid": dataset.uuid,
            "user_id": user_id,
        }
    return None


def _get_dataset_files(user: User, dataset: Dataset) -> list[File]:
    """Get all files for the dataset including those from captures."""
    files = dataset.files.filter(
        is_deleted=False,
        owner=user,
    )
    captures = dataset.captures.filter(
        is_deleted=False,
        owner=user,
    )
    capture_files = File.objects.filter(
        capture__in=captures,
        is_deleted=False,
        owner=user,
    )
    return list(files) + list(capture_files)


def _process_dataset_files(
    all_files: list[File], dataset: Dataset, user: User
) -> tuple[dict | None, str, int, int, TemporaryZipFile | None]:
    """Process dataset files and create zip."""
    if not all_files:
        logger.warning("No files found for dataset %s", dataset.uuid)
        error_message = "No files found in dataset"
        _send_download_error_email(user, dataset, error_message)
        return (
            {
                "status": "error",
                "message": error_message,
                "dataset_uuid": dataset.uuid,
                "total_size": 0,
            },
            "",
            0,
            0,
            None,
        )

    safe_dataset_name = dataset.name.replace(" ", "_")
    zip_filename = f"dataset_{safe_dataset_name}_{dataset.uuid}.zip"

    # Create zip file using the generic function
    zip_file_path, total_size, files_processed = create_zip_from_files(
        all_files, zip_filename
    )

    if files_processed == 0:
        logger.warning("No files were processed for dataset %s", dataset.uuid)
        error_message = "No files could be processed"
        _send_download_error_email(user, dataset, error_message)
        return (
            {
                "status": "error",
                "message": error_message,
                "dataset_uuid": dataset.uuid,
                "total_size": 0,
            },
            "",
            0,
            0,
            None,
        )

    temp_zip = TemporaryZipFile.objects.create(
        file_path=zip_file_path,
        filename=zip_filename,
        file_size=total_size,
        files_processed=files_processed,
        owner=user,
    )

    return None, zip_file_path, total_size, files_processed, temp_zip


@shared_task
def send_dataset_files_email(dataset_uuid: str, user_id: str) -> dict:
    """
    Celery task to create a zip file of dataset files and send it via email.

    Args:
        dataset_uuid: UUID of the dataset to process
        user_id: ID of the user requesting the download

    Returns:
        dict: Task result with status and details
    """
    task_name = "dataset_download"
    user = None
    dataset = None
    temp_zip = None

    try:
        # Validate the request
        error_result, user, dataset = _validate_dataset_download_request(
            dataset_uuid, user_id
        )
        if error_result:
            if user and dataset:
                _send_download_error_email(user, dataset, error_result["message"])
            return error_result

        assert user is not None
        assert dataset is not None

        # Check user lock
        error_result = _check_user_lock(user_id, task_name, user, dataset)
        if error_result:
            return error_result

        # Acquire lock
        error_result = _acquire_user_lock(user_id, task_name, user, dataset)
        if error_result:
            return error_result

        logger.info("Acquired lock for user %s, starting dataset download", user_id)

        # Get dataset files
        all_files = _get_dataset_files(user, dataset)

        # Process files and create zip
        error_result, zip_file_path, total_size, files_processed, temp_zip = (
            _process_dataset_files(all_files, dataset, user)
        )
        if error_result:
            return error_result

        assert temp_zip is not None

        subject = f"Your dataset '{dataset.name}' is ready for download"
        context = {
            "dataset_name": dataset.name,
            "download_url": temp_zip.download_url,
            "file_size": temp_zip.file_size,
            "files_count": temp_zip.files_processed,
            "expires_at": temp_zip.expires_at,
            "site_url": settings.SITE_URL,
        }

        # Send email
        send_email(
            subject=subject,
            recipient_list=[user.email],
            plain_template="emails/dataset_download_ready.txt",
            html_template="emails/dataset_download_ready.html",
            context=context,
        )

        logger.info(
            "Successfully sent dataset download email for %s to %s",
            dataset.uuid,
            user.email,
        )

    except (OSError, ValueError) as e:
        logger.exception(
            "Unexpected error in send_dataset_files_email for dataset %s", dataset_uuid
        )
        error_message = f"An unexpected error occurred: {e!s}"
        if user and dataset:
            _send_download_error_email(user, dataset, error_message)
        return {
            "status": "error",
            "message": error_message,
            "dataset_uuid": dataset_uuid,
            "user_id": user_id,
        }
    else:
        return {
            "status": "success",
            "message": "Dataset files email sent successfully",
            "dataset_uuid": dataset_uuid,
            "files_processed": temp_zip.files_processed if temp_zip else 0,
            "temp_zip_uuid": temp_zip.uuid if temp_zip else None,
        }
    finally:
        if user_id is not None:
            release_user_lock(user_id, task_name)
            logger.info("Released lock for user %s", user_id)


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
def send_capture_files_email(capture_uuid: str, user_id: str) -> dict:
    """
    Celery task to create a zip file of capture files and send it via email.

    Args:
        capture_uuid: UUID of the capture to process
        user_id: ID of the user requesting the download

    Returns:
        dict: Task result with status and details
    """
    # Initialize variables that might be used in finally block
    task_name = "capture_download"

    try:
        # Validate the request
        error_result, user, capture = _validate_capture_download_request(
            capture_uuid, user_id
        )
        if error_result:
            return error_result

        # At this point, user and capture are guaranteed to be not None
        assert user is not None
        assert capture is not None

        # Check if user already has a running task
        if is_user_locked(user_id, task_name):
            logger.warning(
                "User %s already has a capture download task running", user_id
            )
            return {
                "status": "error",
                "message": (
                    "You already have a capture download in progress. "
                    "Please wait for it to complete."
                ),
                "capture_uuid": capture_uuid,
                "user_id": user_id,
            }

        # Try to acquire lock for this user
        if not acquire_user_lock(user_id, task_name):
            logger.warning("Failed to acquire lock for user %s", user_id)
            return {
                "status": "error",
                "message": "Unable to start download. Please try again in a moment.",
                "capture_uuid": capture_uuid,
                "user_id": user_id,
            }

        logger.info("Acquired lock for user %s, starting capture download", user_id)

        # Get all files for the capture
        files = capture.files.filter(
            is_deleted=False,
            owner=user,
        )

        if not files:
            logger.warning("No files found for capture %s", capture_uuid)
            return {
                "status": "error",
                "message": "No files found in capture",
                "capture_uuid": capture_uuid,
                "total_size": 0,
            }

        safe_capture_name = (capture.name or "capture").replace(" ", "_")
        zip_filename = f"capture_{safe_capture_name}_{capture_uuid}.zip"

        # Create zip file using the generic function
        zip_file_path, total_size, files_processed = create_zip_from_files(
            files, zip_filename
        )

        if files_processed == 0:
            logger.warning("No files were processed for capture %s", capture_uuid)
            return {
                "status": "error",
                "message": "No files could be processed",
                "capture_uuid": capture_uuid,
                "total_size": 0,
            }

        temp_zip = TemporaryZipFile.objects.create(
            file_path=zip_file_path,
            filename=zip_filename,
            file_size=total_size,
            files_processed=files_processed,
            owner=user,
        )

        # Send email with download link
        capture_display_name = capture.name or f"Capture {capture_uuid}"
        subject = f"Your capture '{capture_display_name}' is ready for download"

        # Create email context
        context = {
            "capture_name": capture_display_name,
            "download_url": temp_zip.download_url,
            "file_size": total_size,
            "files_count": files_processed,
            "expires_at": temp_zip.expires_at,
        }

        # Render email template
        html_message = render_to_string("emails/capture_download_ready.html", context)
        plain_message = render_to_string("emails/capture_download_ready.txt", context)

        user_email = user.email

        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            html_message=html_message,
        )

        logger.info(
            "Successfully sent capture download email for %s to %s",
            capture_uuid,
            user_email,
        )

        return {
            "status": "success",
            "message": "Capture files email sent successfully",
            "capture_uuid": capture_uuid,
            "files_processed": files_processed,
            "temp_zip_uuid": temp_zip.uuid,
        }

    finally:
        # Always release the lock, even if there was an error
        if user_id is not None:
            release_user_lock(user_id, task_name)
            logger.info("Released lock for user %s", user_id)


def _validate_capture_download_request(
    capture_uuid: str, user_id: str
) -> tuple[dict | None, User | None, Capture | None]:
    """
    Validate capture download request parameters.

    Args:
        capture_uuid: UUID of the capture to download
        user_id: ID of the user requesting the download

    Returns:
        tuple: (error_result, user, capture) where error_result is None if valid
    """
    # Validate user
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.warning("User %s not found for capture download", user_id)
        return (
            {
                "status": "error",
                "message": "User not found",
                "capture_uuid": capture_uuid,
                "user_id": user_id,
            },
            None,
            None,
        )

    # Validate capture
    try:
        capture = Capture.objects.get(
            uuid=capture_uuid,
            owner=user,
            is_deleted=False,
        )
    except Capture.DoesNotExist:
        logger.warning(
            "Capture %s not found or not owned by user %s",
            capture_uuid,
            user_id,
        )
        return (
            {
                "status": "error",
                "message": "Capture not found or access denied",
                "capture_uuid": capture_uuid,
                "user_id": user_id,
            },
            None,
            None,
        )

    return None, user, capture


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


@shared_task
def start_capture_post_processing(
    capture_uuid: str, processing_types: list[str] = None
) -> dict:
    """
    Start post-processing pipeline for a DigitalRF capture.

    This is the main entry point that creates and runs the appropriate
    django-cog pipeline for the requested processing types.

    Args:
        capture_uuid: UUID of the capture to process
        processing_types: List of processing types to run (waterfall, spectrogram, etc.)

    Returns:
        dict: Task result with status and details
    """
    logger.info(f"Starting post-processing pipeline for capture {capture_uuid}")

    try:
        # Get the capture
        capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)

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

        # Import here to avoid circular imports
        from .cog_pipelines import get_pipeline

        # Create and run the appropriate pipeline
        if len(processing_types) > 1:
            pipeline = get_pipeline(
                "capture_post_processing",
                capture_uuid=capture_uuid,
                processing_types=processing_types,
            )
        else:
            pipeline_type = processing_types[0]
            pipeline = get_pipeline(pipeline_type, capture_uuid=capture_uuid)

        # Run the pipeline
        pipeline.run()

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
        ProcessingType.Spectrogram.value: {
            "fft_size": 1024,
            "window_type": "hann",
            "overlap": 0.5,
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
def process_spectrogram_data(capture_uuid: str) -> dict:
    """
    Process DigitalRF data into spectrogram format.

    Args:
        capture_uuid: UUID of the capture to process

    Returns:
        dict: Processing result with file path and metadata
    """
    logger.info(f"Processing spectrogram data for capture {capture_uuid}")

    try:
        capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)

        # Get the temporary directory from previous step
        import tempfile

        temp_dir = tempfile.mkdtemp(prefix=f"spectrogram_{capture_uuid}_")
        temp_path = Path(temp_dir)

        # Reconstruct the files
        capture_files = capture.files.filter(is_deleted=False)
        reconstructed_path = _reconstruct_drf_files(capture, capture_files, temp_path)

        if not reconstructed_path:
            return {
                "status": "error",
                "message": "Failed to reconstruct DigitalRF directory structure",
            }

        # Process the spectrogram data
        spectrogram_result = _convert_drf_to_spectrogram(
            reconstructed_path, capture.channel, ProcessingType.Spectrogram.value
        )

        if spectrogram_result["status"] != "success":
            return spectrogram_result

        return {
            "status": "success",
            "message": "Spectrogram data processed successfully",
            "data_file_path": spectrogram_result["data_file_path"],
            "metadata": spectrogram_result["metadata"],
        }

    except Exception as e:
        logger.exception(f"Error processing spectrogram data: {e}")
        return {
            "status": "error",
            "message": f"Error processing spectrogram data: {e}",
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


def _convert_drf_to_spectrogram(
    drf_path: Path, channel: str, processing_type: str
) -> dict:
    """Convert DigitalRF data to spectrogram format."""
    import tempfile

    import h5py
    import numpy as np
    from digital_rf import DigitalRFReader
    from scipy.signal import spectrogram

    logger.info(
        f"Converting DigitalRF data to spectrogram format for channel {channel}"
    )

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
            metadata_dict = reader.read_metadata(
                start_sample, min(1000, end_sample - start_sample), channel
            )
            if metadata_dict and "center_freq" in metadata_dict:
                center_freq = float(metadata_dict["center_freq"])
        except Exception as e:
            logger.warning(f"Could not read center frequency from metadata: {e}")

        # Read a reasonable amount of data for spectrogram
        max_samples = min(total_samples, int(sample_rate * 10))  # 10 seconds max
        data_array = reader.read_vector(start_sample, max_samples, channel, 0)

        # Processing parameters
        fft_size = 1024
        nperseg = 1024
        noverlap = 512

        # Compute spectrogram
        frequencies, times, Sxx = spectrogram(
            data_array,
            fs=sample_rate,
            nperseg=nperseg,
            noverlap=noverlap,
            nfft=fft_size,
        )

        # Convert to dB
        Sxx_db = 10 * np.log10(Sxx + 1e-12)

        # Create temporary file for spectrogram data
        with tempfile.NamedTemporaryFile(suffix=".h5", delete=False) as temp_file:
            temp_file_path = temp_file.name

        # Store in HDF5 file
        with h5py.File(temp_file_path, "w") as h5_file:
            # Create datasets
            spectrogram_group = h5_file.create_group("spectrogram")

            # Store metadata
            spectrogram_group.attrs["center_frequency"] = center_freq
            spectrogram_group.attrs["sample_rate"] = sample_rate
            spectrogram_group.attrs["fft_size"] = fft_size
            spectrogram_group.attrs["nperseg"] = nperseg
            spectrogram_group.attrs["noverlap"] = noverlap
            spectrogram_group.attrs["channel"] = channel

            # Store data
            spectrogram_group.create_dataset(
                "frequencies", data=frequencies, compression="gzip", compression_opts=6
            )
            spectrogram_group.create_dataset(
                "times", data=times, compression="gzip", compression_opts=6
            )
            spectrogram_group.create_dataset(
                "data",
                data=Sxx_db.astype(np.float32),
                compression="gzip",
                compression_opts=6,
            )

        metadata = {
            "center_frequency": center_freq,
            "sample_rate": sample_rate,
            "fft_size": fft_size,
            "nperseg": nperseg,
            "noverlap": noverlap,
            "frequencies_shape": frequencies.shape,
            "times_shape": times.shape,
            "data_shape": Sxx_db.shape,
            "channel": channel,
        }

        return {
            "status": "success",
            "message": "Spectrogram data converted successfully",
            "data_file_path": temp_file_path,
            "metadata": metadata,
        }

    except Exception as e:
        logger.exception(f"Error converting DigitalRF to spectrogram: {e}")
        return {
            "status": "error",
            "message": f"Error converting DigitalRF data: {e}",
        }
