import datetime
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any
from typing import cast

import redis
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from loguru import logger
from redis import Redis

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import ProcessingType
from sds_gateway.api_methods.models import TemporaryZipFile
from sds_gateway.api_methods.models import user_has_access_to_item
from sds_gateway.api_methods.utils.sds_files import sanitize_path_rel_to_user
from sds_gateway.users.models import User

# ruff: noqa: PLC0415


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
def check_celery_task(message: str = "Hello from Celery!") -> str:
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
def check_email_task(email_address: str = "test@example.com") -> str:
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
def cleanup_expired_temp_zips() -> dict[str, str | int]:
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


def get_user_task_status(
    user_id: str, task_name: str
) -> dict[str, str | int | bool | None]:
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
            timestamp_str_or_none: str | None = None
            if lock_timestamp:
                try:
                    timestamp_str_or_none = cast("str", lock_timestamp.decode("utf-8"))
                except (AttributeError, UnicodeDecodeError):
                    timestamp_str_or_none = str(lock_timestamp)

            ttl_value = 0
            if ttl is not None:
                try:
                    ttl_value = max(0, int(ttl))  # pyright: ignore[reportArgumentType]
                except (ValueError, TypeError):
                    ttl_value = 0

            return {
                "is_locked": True,
                "lock_timestamp": timestamp_str_or_none,
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


@shared_task
def start_capture_post_processing(
    capture_uuid: str, processing_types: list[str] | None = None
) -> dict:
    """
    Start post-processing pipeline for a DigitalRF capture.

    This is the main entry point that launches the django-cog pipeline.
    Setup and validation are now handled within the pipeline itself.

    Args:
        capture_uuid: UUID of the capture to process
        processing_types: List of processing types to run (waterfall, spectrogram, etc.)
    """
    logger.info(f"Starting post-processing pipeline for capture {capture_uuid}")

    try:
        # Set default processing types if not specified
        if not processing_types:
            processing_types = [ProcessingType.Waterfall.value]

        # Get the appropriate pipeline from the database
        from sds_gateway.api_methods.models import get_latest_pipeline_by_base_name

        # For now, we only support waterfall processing
        if "waterfall" in processing_types:
            pipeline_name = ProcessingType.Waterfall.get_pipeline_name()
            pipeline = get_latest_pipeline_by_base_name(pipeline_name)
            if not pipeline:
                error_msg = (
                    f"No {pipeline_name} pipeline found. Please run setup_pipelines."
                )
                raise ValueError(error_msg)  # noqa: TRY301

            # Launch the pipeline with runtime arguments
            # Setup and validation will be handled by the setup stage in the pipeline
            pipeline.launch(
                capture_uuid=capture_uuid, processing_types=processing_types
            )
        else:
            error_msg = f"Unsupported processing types: {processing_types}"
            raise ValueError(error_msg)  # noqa: TRY301

        return {
            "status": "success",
            "message": (
                f"Post-processing pipeline started for {len(processing_types)} types"
            ),
            "capture_uuid": capture_uuid,
            "processing_types": processing_types,
        }

    except Capture.DoesNotExist:
        error_msg = f"Capture {capture_uuid} not found"
        logger.error(error_msg)
        raise
    except Exception as e:
        error_msg = f"Unexpected error in post-processing pipeline: {e}"
        logger.exception(error_msg)
        raise


def _create_error_response(
    status: str,
    message: str,
    item_uuid: str,
    user_id: str | None = None,
    total_size: int = 0,
) -> dict[str, str | int]:
    """Create a standardized error response."""
    response: dict[str, str | int] = {
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
) -> tuple[dict[str, str | int] | None, str | None, int | None, int | None]:
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
) -> dict[str, str | int] | None:
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
    user: User | None,
    item: Any,
    item_type: ItemType | None,
    item_uuid: str,
    e: Exception,
) -> dict[str, Any]:
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
    if user is not None and item is not None and item_type is not None:
        _send_item_download_error_email(user, item, item_type, error_message)
    return _create_error_response("error", error_message, item_uuid)


@shared_task(
    time_limit=30 * 60, soft_time_limit=25 * 60
)  # 30 min hard limit, 25 min soft limit
def send_item_files_email(  # noqa: C901
    item_uuid: str, user_id: str, item_type: str | ItemType
) -> dict[str, str | int]:
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
    item = None
    item_type_enum: ItemType | None = None
    result = None
    user = None

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
        item_type_enum = item_type

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
        if user is not None and item is not None and item_type_enum is not None:
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
) -> tuple[dict[str, str | int] | None, User | None, Any]:
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
