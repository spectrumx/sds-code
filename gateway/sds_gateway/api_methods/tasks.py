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
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import TemporaryZipFile
from sds_gateway.api_methods.utils.sds_files import sanitize_path_rel_to_user


def get_redis_client() -> Redis:
    """Get Redis client for locking."""
    return Redis.from_url(settings.CELERY_BROKER_URL)


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


@shared_task
def send_dataset_files_email(dataset_uuid: str, user_email: str) -> dict:
    """
    Celery task to create a zip file of dataset files and send it via email.

    Args:
        dataset_uuid: UUID of the dataset to process
        user_email: Email address to send the files to

    Returns:
        dict: Task result with status and details
    """
    # Get the dataset and user
    try:
        dataset = Dataset.objects.get(uuid=dataset_uuid, is_deleted=False)
        user = dataset.owner

        if not user:
            logger.error("Dataset %s has no owner", dataset_uuid)
            return {
                "status": "error",
                "message": "Dataset has no owner",
                "dataset_uuid": dataset_uuid,
            }

        user_id = str(user.id)
        task_name = "dataset_download"

        # Check if user already has a running task
        if is_user_locked(user_id, task_name):
            logger.warning(
                "User %s already has a dataset download task running", user_id
            )
            return {
                "status": "error",
                "message": (
                    "You already have a dataset download in progress. "
                    "Please wait for it to complete."
                ),
                "dataset_uuid": dataset_uuid,
                "user_id": user_id,
            }

        # Try to acquire lock for this user
        if not acquire_user_lock(user_id, task_name, timeout=600):  # 10 minute timeout
            logger.warning("Failed to acquire lock for user %s", user_id)
            return {
                "status": "error",
                "message": "Unable to start download. Please try again in a moment.",
                "dataset_uuid": dataset_uuid,
                "user_id": user_id,
            }

        logger.info("Acquired lock for user %s, starting dataset download", user_id)

    except Dataset.DoesNotExist:
        logger.error("Dataset %s not found", dataset_uuid)
        return {
            "status": "error",
            "message": "Dataset not found",
            "dataset_uuid": dataset_uuid,
        }
    except Exception:
        logger.exception("Error getting dataset %s", dataset_uuid)
        return {
            "status": "error",
            "message": (
                "An unexpected error occurred while accessing the dataset. "
                "Please try again later."
            ),
            "dataset_uuid": dataset_uuid,
        }

    try:
        # Get all files and captures for the dataset
        files = File.objects.filter(
            dataset=dataset,
            is_deleted=False,
        )

        captures = dataset.captures.filter(is_deleted=False)

        # Get files from captures
        capture_files = File.objects.filter(
            capture__in=captures,
            is_deleted=False,
        )

        # Combine all files
        all_files = list(files) + list(capture_files)

        if not all_files:
            logger.warning("No files found for dataset %s", dataset_uuid)
            return {
                "status": "error",
                "message": "No files found in dataset",
                "dataset_uuid": dataset_uuid,
                "total_size": 0,
            }

        safe_dataset_name = dataset.name.replace(" ", "_")
        zip_filename = f"dataset_{safe_dataset_name}_{dataset_uuid}.zip"

        # Create zip file using the generic function
        zip_file_path, total_size, files_processed = create_zip_from_files(
            all_files, zip_filename
        )

        if files_processed == 0:
            logger.warning("No files were processed for dataset %s", dataset_uuid)
            return {
                "status": "error",
                "message": "No files could be processed",
                "dataset_uuid": dataset_uuid,
                "total_size": 0,
            }

        # Get the user from the dataset owner
        user = dataset.owner

        temp_zip = TemporaryZipFile.objects.create(
            file_path=zip_file_path,
            filename=zip_filename,
            file_size=total_size,
            files_processed=files_processed,
            owner=user,
        )

        # Send email with download link
        subject = f"Your dataset '{dataset.name}' is ready for download"

        # Create email context
        context = {
            "dataset_name": dataset.name,
            "download_url": temp_zip.download_url,
            "file_size": total_size,
            "files_count": files_processed,
            "expires_at": temp_zip.expires_at,
        }

        # Render email template
        html_message = render_to_string("emails/dataset_download_ready.html", context)
        plain_message = render_to_string("emails/dataset_download_ready.txt", context)

        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user_email],
            html_message=html_message,
        )

        logger.info(
            "Successfully sent dataset download email for %s to %s",
            dataset_uuid,
            user_email,
        )

        return {
            "status": "success",
            "message": "Dataset files email sent successfully",
            "dataset_uuid": dataset_uuid,
        }
    except (ValueError, AttributeError, OSError):
        logger.exception("Error getting dataset %s", dataset_uuid)
        return {
            "status": "error",
            "message": (
                "An unexpected error occurred while accessing the dataset. "
                "Please try again later."
            ),
            "dataset_uuid": dataset_uuid,
        }
    except Exception:
        logger.exception("Error getting dataset %s", dataset_uuid)
        return {
            "status": "error",
            "message": (
                "An unexpected error occurred while accessing the dataset. "
                "Please try again later."
            ),
            "dataset_uuid": dataset_uuid,
        }
    finally:
        # Always release the lock, even if there was an error
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
    # Directory is mounted as a volume, so no need to create it

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

                # Soft delete the database record and mark as expired
                temp_zip.soft_delete()
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
        return {
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
