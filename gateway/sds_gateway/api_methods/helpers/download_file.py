import logging

from django.conf import settings
from minio.error import MinioException
from minio.error import S3Error

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
    minio_response = None
    file_content = None

    try:
        # Get the file content from MinIO
        minio_response = client.get_object(
            bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
            object_name=target_file.file.name,
        )
        file_content = minio_response.read()
        logger.info("Successfully retrieved file: %s", target_file.file.name)

    except MinioException:
        logger.exception("MinIO error downloading file %s", target_file.file.name)
        raise
    except S3Error:
        logger.exception("S3 error downloading file %s", target_file.file.name)
        raise
    except Exception:
        logger.exception("Unexpected error downloading file %s", target_file.file.name)
        error_msg = f"Failed to download file {target_file.file.name}"
        raise FileDownloadError(error_msg) from None
    finally:
        if minio_response:
            try:
                minio_response.close()
                minio_response.release_conn()
            except OSError:
                logger.warning(
                    "Error closing MinIO response for %s", target_file.file.name
                )

    if file_content is None:
        error_msg = (
            f"Failed to download file {target_file.file.name}: No content retrieved"
        )
        raise FileDownloadError(error_msg)

    return file_content
