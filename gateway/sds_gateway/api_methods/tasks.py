import datetime
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
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
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
