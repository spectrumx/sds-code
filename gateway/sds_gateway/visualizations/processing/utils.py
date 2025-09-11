"""Shared utilities for visualization processing."""

import datetime
from pathlib import Path

from loguru import logger


def reconstruct_drf_files(capture, capture_files, temp_path: Path) -> Path | None:
    """Reconstruct DigitalRF directory structure from SDS files."""
    # Import utilities here to avoid Django app registry issues
    from django.conf import settings

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
            file_path = Path(
                f"{capture_dir}/{file_obj.directory}/{file_obj.name}"
            ).resolve()
            assert file_path.is_relative_to(temp_path), (
                f"'{file_path=}' must be a subdirectory of '{temp_path=}'"
            )
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Download the file from MinIO
            minio_client.fget_object(
                bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
                object_name=file_obj.file.name,
                file_path=str(file_path),
            )

        # Find the DigitalRF root directory (parent of the channel directory)
        import os

        for root, _dirs, files in os.walk(capture_dir):
            if "drf_properties.h5" in files:
                # The DigitalRF root is the parent of the channel directory
                drf_root = Path(root).parent
                logger.info(f"Found DigitalRF root at: {drf_root}")
                return drf_root
        logger.error("Could not find DigitalRF properties file")
        return None  # noqa: TRY300

    except Exception as e:  # noqa: BLE001
        logger.exception(f"Error reconstructing DigitalRF files: {e}")
        return None


def store_processed_data(
    capture_uuid: str,
    processing_type: str,
    curr_file_path: str,
    new_filename: str,
    metadata: dict | None = None,
) -> dict:
    """
    Store processed data back to SDS storage as a file.

    Args:
        capture_uuid: UUID of the capture
        processing_type: Type of processed data (waterfall, spectrogram, etc.)
        file_path: Path to the file to store
        filename: New name for the stored file
        metadata: Metadata to store

    Returns:
        dict: Storage result
    """
    # Import models here to avoid Django app registry issues
    from sds_gateway.api_methods.models import Capture
    from sds_gateway.visualizations.models import PostProcessedData

    logger.info(f"Storing {processing_type} file for capture {capture_uuid}")

    try:
        capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)

        # Get the processed data record
        processed_data = PostProcessedData.objects.filter(
            capture=capture,
            processing_type=processing_type,
        ).first()

        if not processed_data:
            error_msg = f"No processed data record found for {processing_type}"
            raise ValueError(error_msg)  # noqa: TRY301

        # Store the file
        processed_data.set_processed_data_file(curr_file_path, new_filename)

        # Update metadata if provided
        if metadata:
            processed_data.metadata.update(metadata)

        # Add storage metadata
        processed_data.metadata.update(
            {
                "stored_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "data_format": "file",
                "file_size": processed_data.data_file.size,
            }
        )
        processed_data.save()

        logger.info(f"Stored file {new_filename} for {processing_type} data")

        return {  # noqa: TRY300
            "status": "success",
            "message": f"{processing_type} file stored successfully",
            "file_name": new_filename,
        }

    except Exception as e:
        logger.exception(f"Error storing {processing_type} file: {e}")
        raise


def _create_or_reset_processed_data(capture, processing_type: str):
    """Create or reset a PostProcessedData record for a capture and processing type.

    Args:
        capture: The capture to create processed data for
        processing_type: Type of processing (waterfall, spectrogram, etc.)

    Returns:
        PostProcessedData: The created or reset record
    """
    # Import models here to avoid Django app registry issues
    from sds_gateway.visualizations.models import PostProcessedData
    from sds_gateway.visualizations.models import ProcessingStatus

    # Try to get existing record
    processed_data, newly_created = PostProcessedData.objects.get_or_create(
        capture=capture,
        processing_type=processing_type,
        processing_parameters={},  # Default empty parameters
        defaults={
            "processing_status": ProcessingStatus.Pending.value,
            "metadata": {},
        },
    )

    if not newly_created:
        # Reset existing record
        processed_data.processing_status = ProcessingStatus.Pending.value
        processed_data.processing_error = ""
        processed_data.processed_at = None
        processed_data.pipeline_id = ""
        processed_data.metadata = {}
        if processed_data.data_file:
            processed_data.data_file.delete(save=False)
        processed_data.save()

    return processed_data
