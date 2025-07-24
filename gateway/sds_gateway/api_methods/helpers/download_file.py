import logging
import tempfile
from pathlib import Path

from django.conf import settings
from minio.error import MinioException

from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.utils.minio_client import get_minio_client

logger = logging.getLogger(__name__)


class FileDownloadError(Exception):
    """Custom exception for file download errors."""


def download_file(target_file: File) -> bytes:
    """
    Download a file from MinIO storage.

    Args:
        target_file: File model instance to download

    Returns:
        bytes: The file content

    Raises:
        MinioException: If there's an error with MinIO operations
        S3Error: If there's an S3-specific error
        FileDownloadError: For other unexpected errors
    """
    client = get_minio_client()
    temp_file = None
    file_content = None
    file_path = None

    try:
        # Create a temporary file to download to
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file_path = temp_file.name

        # Download the file
        client.fget_object(
            bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
            object_name=target_file.file.name,
            file_path=temp_file_path,
        )

        # Read the downloaded file
        file_path = Path(temp_file_path)
        with file_path.open("rb") as f:
            file_content = f.read()

        logger.info("Successfully retrieved file: %s", target_file.file.name)

    except MinioException:
        logger.exception("MinIO error downloading file %s", target_file.file.name)
        raise
    finally:
        # Clean up temporary file
        if temp_file and temp_file_path and Path(temp_file_path).exists():
            try:
                if file_path is None:
                    file_path = Path(temp_file_path)
                file_path.unlink()
            except OSError:
                logger.warning("Could not delete temporary file: %s", temp_file_path)

    if file_content is None:
        error_msg = f"Failed to download file {target_file.name}: No content retrieved"
        raise FileDownloadError(error_msg)

    return file_content
