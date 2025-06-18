import io
import zipfile
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from loguru import logger

from sds_gateway.api_methods.helpers.dataset_files import get_dataset_files
from sds_gateway.api_methods.helpers.download_file import download_file
from sds_gateway.api_methods.models import Dataset


@shared_task(bind=True)
def send_dataset_files_email(self, dataset_uuid: str, user_email: str) -> dict:
    """
    Celery task to download dataset files, create a zip archive,
    and email it to the user.

    Args:
        dataset_uuid: UUID of the dataset to process
        user_email: Email address to send the files to

    Returns:
        dict: Task result with status and details
    """
    try:
        # Get the dataset
        dataset = Dataset.objects.get(uuid=dataset_uuid, is_deleted=False)
        logger.info("Processing dataset %s for user %s", dataset_uuid, user_email)

        # Get all files associated with the dataset
        files = get_dataset_files(dataset)

        if not files:
            logger.warning("No files found for dataset %s", dataset_uuid)
            return {
                "status": "warning",
                "message": "No files found in the dataset",
                "files_processed": 0,
                "total_size": 0,
            }

        # Create zip file in memory
        zip_buffer = io.BytesIO()
        total_size = 0
        files_processed = 0

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for file_obj in files:
                try:
                    # Download file content
                    file_content = download_file(file_obj)

                    # Create a safe filename for the zip
                    safe_filename = f"{file_obj.name}"
                    if file_obj.directory and file_obj.directory != "files/":
                        # Include directory structure in zip
                        rel_path = Path(file_obj.directory).relative_to(Path("files/"))
                        safe_filename = f"{rel_path}/{file_obj.name}"

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

        if files_processed == 0:
            logger.error(
                "No files were successfully processed for dataset %s", dataset_uuid
            )
            return {
                "status": "error",
                "message": "Failed to process any files",
                "files_processed": 0,
                "total_size": 0,
            }

        # Prepare email
        zip_buffer.seek(0)
        zip_filename = f"dataset_{dataset.name}_{dataset_uuid}.zip"

        email = EmailMessage(
            subject=f"Dataset Files: {dataset.name}",
            body=(
                f'Hello,\n\nYour dataset "{dataset.name}" files have been prepared '
                f"and are attached to this email.\n\n"
                f"Dataset Details:\n- Name: {dataset.name}\n- Description: "
                f"{dataset.description or 'No description provided'}\n"
                f"- Files processed: {files_processed}\n- Total size: "
                f"{total_size / (1024 * 1024):.2f} MB\n\n"
                "The zip file contains all files associated with this dataset, "
                "including files from linked captures.\n\n"
                "Best regards,\nSpectrumX Data System"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user_email],
        )

        email.attach(zip_filename, zip_buffer.getvalue(), "application/zip")

        # Send email
        email.send()

        logger.info(
            "Successfully sent dataset %s files to %s", dataset_uuid, user_email
        )

    except Dataset.DoesNotExist:
        logger.error("Dataset %s not found", dataset_uuid)
        return {
            "status": "error",
            "message": "Dataset not found",
            "files_processed": 0,
            "total_size": 0,
        }
    except (OSError, ValueError):
        logger.exception("Error processing dataset %s", dataset_uuid)
        return {
            "status": "error",
            "message": "Failed to process dataset",
            "files_processed": 0,
            "total_size": 0,
        }
    else:
        return {
            "status": "success",
            "message": f"Dataset files sent successfully to {user_email}",
            "files_processed": files_processed,
            "total_size": total_size,
            "zip_filename": zip_filename,
        }
