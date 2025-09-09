"""Django-cog pipeline configurations for visualization processing."""

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from django.conf import settings
from django_cog import cog
from loguru import logger

from sds_gateway.visualizations.processing.spectrogram import (
    generate_spectrogram_from_drf,
)
from sds_gateway.visualizations.processing.waterfall import (
    convert_drf_to_waterfall_json,
)


# Pipeline configuration functions for Django admin setup
def get_visualization_pipeline_config() -> dict[str, Any]:
    """Get configuration for visualization processing pipeline.

    This should be used to set up the pipeline in Django admin with the following
    structure:

    Pipeline:
    - Name: "visualization_processing"
    - Schedule: None (manual launch)
    - Prevent overlapping runs: False (allow concurrent processing)

    Stages:
    1. "setup_stage" - setup_post_processing_cog (validates capture, creates records)
    2. "waterfall_stage" - process_waterfall_data_cog (processes waterfall data)
    3. "spectrogram_stage" - process_spectrogram_data_cog (processes spectrogram data)

    Tasks in each stage:
    - setup_stage: setup_post_processing_cog (capture_uuid and processing_types passed
      as runtime args)
    - waterfall_stage: process_waterfall_data_cog (capture_uuid passed as runtime arg,
      depends on setup_stage)
    - spectrogram_stage: process_spectrogram_data_cog (capture_uuid passed as runtime
      arg, depends on setup_stage, independent of waterfall_stage)
    """

    return {
        "pipeline_name": "visualization_processing",
        "prevent_overlapping_runs": False,
        "stages": [
            {
                "name": "setup_stage",
                "description": "Setup post-processing (validate capture, create "
                "records for waterfall and spectrogram)",
                "tasks": [
                    {
                        "name": "setup_processing",
                        "cog": "setup_post_processing_cog",
                        "args": {},
                        "description": "Setup post-processing",
                    }
                ],
            },
            {
                "name": "waterfall_stage",
                "description": "Process waterfall data (downloads, processes, and "
                "stores)",
                "depends_on": ["setup_stage"],
                "tasks": [
                    {
                        "name": "process_waterfall",
                        "cog": "process_waterfall_data_cog",
                        "args": {},
                        "description": "Process waterfall data",
                    }
                ],
            },
            {
                "name": "spectrogram_stage",
                "description": "Process spectrogram data (downloads, processes, and "
                "stores)",
                "depends_on": ["setup_stage"],
                "tasks": [
                    {
                        "name": "process_spectrogram",
                        "cog": "process_spectrogram_data_cog",
                        "args": {},
                        "description": "Process spectrogram data",
                    }
                ],
            },
        ],
    }


# Pipeline registry for easy access
PIPELINE_CONFIGS = {
    "visualization": get_visualization_pipeline_config,  # Unified pipeline for all
    # visualizations
}


def get_pipeline_config(pipeline_type: str) -> dict[str, Any]:
    """Get a pipeline configuration by type.

    Args:
        pipeline_type: Type of pipeline configuration to get

    Returns:
        Pipeline configuration dict
    """
    config_func = PIPELINE_CONFIGS.get(pipeline_type)
    if not config_func:
        error_msg = f"Unknown pipeline type: {pipeline_type}"
        raise ValueError(error_msg)

    return config_func()


# Cog functions (pipeline steps)
@cog
def setup_post_processing_cog(capture_uuid: str, processing_types: list[str]) -> None:
    """Setup post-processing for a capture.

    Args:
        capture_uuid: UUID of the capture to process
        processing_types: List of processing types to run
    Returns:
        None
    """

    # imports to run when the app is ready
    from sds_gateway.api_methods.models import Capture  # noqa: PLC0415
    from sds_gateway.api_methods.models import CaptureType  # noqa: PLC0415

    try:
        logger.info(f"Starting setup for capture {capture_uuid}")

        # Get the capture with retry mechanism for transaction timing issues
        capture: Capture | None = None
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

                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    # Final attempt failed
                    error_msg = (
                        f"Capture {capture_uuid} not found after {max_retries} attempts"
                    )
                    logger.error(error_msg)
                    raise ValueError(error_msg) from None

        # At this point, capture should not be None due to the retry logic above
        assert capture is not None, (
            f"Capture {capture_uuid} should have been found by now"
        )

        # Validate capture type
        if capture.capture_type != CaptureType.DigitalRF:
            error_msg = f"Capture {capture_uuid} is not a DigitalRF capture"
            raise ValueError(error_msg)  # noqa: TRY301

        # Set default processing types if not specified
        if not processing_types:
            error_msg = "No processing types specified"
            raise ValueError(error_msg)  # noqa: TRY301

        # Create PostProcessedData records for each processing type
        for processing_type in processing_types:
            _create_or_reset_processed_data(capture, processing_type)

        logger.info(f"Completed setup for capture {capture_uuid}")
    except Exception as e:
        logger.error(f"Setup failed for capture {capture_uuid}: {e}")
        raise


@cog
def process_waterfall_data_cog(  # noqa: PLR0915
    capture_uuid: str,
    processing_types: list[str],
) -> dict[str, Any]:
    """Process waterfall data for a capture.

    Args:
        capture_uuid: UUID of the capture to process
        processing_types: List of processing types to run

    Returns:
        Dict with status and processed data info
    """

    # imports to run when the app is ready
    from sds_gateway.api_methods.models import Capture  # noqa: PLC0415
    from sds_gateway.visualizations.models import PostProcessedData  # noqa: PLC0415
    from sds_gateway.visualizations.models import ProcessingType  # noqa: PLC0415
    from sds_gateway.visualizations.processing.utils import (  # noqa: PLC0415
        reconstruct_drf_files,
    )
    from sds_gateway.visualizations.processing.utils import (  # noqa: PLC0415
        store_processed_data,
    )

    # Check if waterfall processing is requested
    if processing_types and "waterfall" not in processing_types:
        logger.info(
            f"Skipping waterfall processing for capture {capture_uuid} - not requested"
        )
        return {
            "status": "skipped",
            "message": "Waterfall processing not requested",
            "capture_uuid": capture_uuid,
        }

    logger.info(f"Processing waterfall JSON data for capture {capture_uuid}")

    try:
        capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)

        # Get the processed data record and mark processing as started
        processed_data = PostProcessedData.objects.filter(
            capture=capture,
            processing_type=ProcessingType.Waterfall.value,
        ).first()

        if not processed_data:
            error_msg = (
                f"No processed data record found for {ProcessingType.Waterfall.value}"
            )
            raise ValueError(error_msg)  # noqa: TRY301

        # Mark processing as started
        processed_data.mark_processing_started(pipeline_id="django_cog_pipeline")

        # Use built-in temporary directory context manager
        with tempfile.TemporaryDirectory(
            prefix=f"waterfall_{capture_uuid}_"
        ) as temp_dir:
            temp_path = Path(temp_dir)

            try:
                # Reconstruct the DigitalRF files for processing
                capture_files = capture.files.filter(is_deleted=False)
                reconstructed_path = reconstruct_drf_files(
                    capture, capture_files, temp_path
                )

                if not reconstructed_path:
                    error_msg = "Failed to reconstruct DigitalRF directory structure"
                    processed_data.mark_processing_failed(error_msg)
                    raise ValueError(error_msg)  # noqa: TRY301

                # Process the waterfall data in JSON format
                waterfall_result = convert_drf_to_waterfall_json(
                    reconstructed_path,
                    capture.channel,
                    ProcessingType.Waterfall.value,
                )

                if waterfall_result["status"] != "success":
                    processed_data.mark_processing_failed(waterfall_result["message"])
                    raise ValueError(waterfall_result["message"])  # noqa: TRY301

                # Create a temporary JSON file
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False
                ) as temp_file:
                    json.dump(waterfall_result["json_data"], temp_file, indent=2)
                    temp_file_path = temp_file.name
                    logger.info(f"Created temporary JSON file at {temp_file_path}")

                try:
                    # Store the JSON file
                    new_filename = f"waterfall_{capture_uuid}.json"

                    store_result = store_processed_data(
                        capture_uuid,
                        ProcessingType.Waterfall.value,
                        temp_file_path,
                        new_filename,
                        waterfall_result["metadata"],
                    )

                    if store_result["status"] != "success":
                        processed_data.mark_processing_failed(store_result["message"])
                        raise ValueError(store_result["message"])

                    # Mark processing as completed
                    processed_data.mark_processing_completed()

                    logger.info(
                        f"Completed waterfall processing for capture {capture_uuid}"
                    )
                    return {
                        "status": "success",
                        "capture_uuid": capture_uuid,
                        "message": (
                            "Waterfall JSON data processed and stored successfully"
                        ),
                        "json_data": waterfall_result["json_data"],
                        "metadata": waterfall_result["metadata"],
                        "store_result": store_result,
                    }

                finally:
                    # Clean up temporary file
                    if "temp_file_path" in locals():
                        Path(temp_file_path).unlink(missing_ok=True)
                        logger.info(f"Cleaned up temporary file {temp_file_path}")

            except Exception as e:
                # Mark processing as failed
                processed_data.mark_processing_failed(f"Processing failed: {e!s}")
                raise

    except Exception as e:
        logger.error(f"Waterfall processing failed for capture {capture_uuid}: {e}")
        raise


@cog
def process_spectrogram_data_cog(
    capture_uuid: str, processing_types: list[str]
) -> dict[str, Any]:
    """Process spectrogram data for a capture.

    Args:
        capture_uuid: UUID of the capture to process
        processing_types: List of processing types to run

    Returns:
        Dict with status and processed data info
    """

    # imports to run when the app is ready
    from sds_gateway.api_methods.models import Capture  # noqa: PLC0415
    from sds_gateway.visualizations.models import PostProcessedData  # noqa: PLC0415
    from sds_gateway.visualizations.models import ProcessingType  # noqa: PLC0415
    from sds_gateway.visualizations.processing.utils import (  # noqa: PLC0415
        reconstruct_drf_files,
    )
    from sds_gateway.visualizations.processing.utils import (  # noqa: PLC0415
        store_processed_data,
    )

    # Check if spectrogram feature is enabled
    if not settings.EXPERIMENTAL_SPECTROGRAM:
        logger.info(
            f"Skipping spectrogram processing for capture {capture_uuid} - "
            f"experimental feature disabled"
        )
        return {
            "status": "skipped",
            "message": "Spectrogram feature is not enabled",
            "capture_uuid": capture_uuid,
        }

    # Check if spectrogram processing is requested
    if processing_types and "spectrogram" not in processing_types:
        logger.info(
            f"Skipping spectrogram processing for capture {capture_uuid} - not "
            f"requested"
        )
        return {
            "status": "skipped",
            "message": "Spectrogram processing not requested",
            "capture_uuid": capture_uuid,
        }

    logger.info(f"Processing spectrogram data for capture {capture_uuid}")

    try:
        capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)

        # Get the processed data record and mark processing as started
        processed_data = PostProcessedData.objects.filter(
            capture=capture,
            processing_type=ProcessingType.Spectrogram.value,
        ).first()

        if not processed_data:
            error_msg = (
                f"No processed data record found for {ProcessingType.Spectrogram.value}"
            )
            raise ValueError(error_msg)  # noqa: TRY301

        # Mark processing as started
        processed_data.mark_processing_started(pipeline_id="django_cog_pipeline")

        # Use built-in temporary directory context manager
        with tempfile.TemporaryDirectory(
            prefix=f"spectrogram_{capture_uuid}_"
        ) as temp_dir:
            temp_path = Path(temp_dir)

            try:
                # Reconstruct the DigitalRF files for processing

                capture_files = capture.files.filter(is_deleted=False)
                reconstructed_path = reconstruct_drf_files(
                    capture, capture_files, temp_path
                )

                if not reconstructed_path:
                    error_msg = "Failed to reconstruct DigitalRF directory structure"
                    processed_data.mark_processing_failed(error_msg)
                    raise ValueError(error_msg)  # noqa: TRY301

                # Generate spectrogram
                spectrogram_result = generate_spectrogram_from_drf(
                    reconstructed_path,
                    capture.channel,
                    ProcessingType.Spectrogram.value,
                )

                if spectrogram_result["status"] != "success":
                    processed_data.mark_processing_failed(spectrogram_result["message"])
                    raise ValueError(spectrogram_result["message"])  # noqa: TRY301

                # Store the spectrogram image
                store_result = store_processed_data(
                    capture_uuid,
                    ProcessingType.Spectrogram.value,
                    spectrogram_result["image_path"],
                    f"spectrogram_{capture_uuid}.png",
                    spectrogram_result["metadata"],
                )

                if store_result["status"] != "success":
                    processed_data.mark_processing_failed(store_result["message"])
                    raise ValueError(store_result["message"])  # noqa: TRY301

                # Mark processing as completed
                processed_data.mark_processing_completed()

                logger.info(
                    f"Completed spectrogram processing for capture {capture_uuid}"
                )
                return {
                    "status": "success",
                    "capture_uuid": capture_uuid,
                    "message": "Spectrogram processed and stored successfully",
                    "metadata": spectrogram_result["metadata"],
                    "store_result": store_result,
                }

            except Exception as e:
                # Mark processing as failed
                processed_data.mark_processing_failed(f"Processing failed: {e!s}")
                raise

    except Exception as e:
        logger.error(f"Spectrogram processing failed for capture {capture_uuid}: {e}")
        raise


# Helper functions
def _create_or_reset_processed_data(capture, processing_type: str):
    """Create or reset a PostProcessedData record for a capture and processing type.

    Args:
        capture: The capture to create processed data for
        processing_type: Type of processing (waterfall, spectrogram, etc.)

    Returns:
        PostProcessedData: The created or reset record
    """

    # imports to run when app is ready
    from sds_gateway.visualizations.models import PostProcessedData  # noqa: PLC0415
    from sds_gateway.visualizations.models import ProcessingStatus  # noqa: PLC0415

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
