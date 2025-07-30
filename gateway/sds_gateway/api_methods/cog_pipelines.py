"""Django-cog pipeline configurations for post-processing."""

from typing import Any

from django_cog import cog
from loguru import logger


@cog
def process_waterfall_data_cog(
    capture_uuid: str, max_slices: int = 100
) -> dict[str, Any]:
    """Process waterfall data for a capture.

    Args:
        capture_uuid: UUID of the capture to process
        max_slices: Maximum number of slices to process (default: 100)

    Returns:
        Dict with status and processed data info
    """
    logger.info(f"Processing waterfall JSON data for capture {capture_uuid}")

    try:
        # Import models here to avoid Django app registry issues
        from .models import Capture
        from .models import ProcessingType
        from .tasks import convert_drf_to_waterfall_json
        from .tasks import reconstruct_drf_files
        from .tasks import store_processed_data

        capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)

        # Create temporary directory for processing
        import os
        import tempfile
        from pathlib import Path

        temp_dir = tempfile.mkdtemp(prefix=f"waterfall_{capture_uuid}_")
        temp_path = Path(temp_dir)

        # Reconstruct the DigitalRF files for processing
        capture_files = capture.files.filter(is_deleted=False)
        reconstructed_path = reconstruct_drf_files(capture, capture_files, temp_path)

        if not reconstructed_path:
            return {
                "status": "error",
                "message": "Failed to reconstruct DigitalRF directory structure",
            }

        # Process the waterfall data in JSON format
        waterfall_result = convert_drf_to_waterfall_json(
            reconstructed_path,
            capture.channel,
            ProcessingType.Waterfall.value,
            max_slices,
        )

        if waterfall_result["status"] != "success":
            return waterfall_result

        # Create a temporary JSON file
        import json

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as temp_file:
            json.dump(waterfall_result["json_data"], temp_file, indent=2)
            temp_file_path = temp_file.name

        # Store the JSON file
        filename = f"waterfall_{capture_uuid}.json"
        store_result = store_processed_data(
            capture_uuid,
            ProcessingType.Waterfall.value,
            temp_file_path,
            filename,
            waterfall_result["metadata"],
        )

        # Clean up temporary file
        os.unlink(temp_file_path)

        logger.info(f"Completed waterfall processing for capture {capture_uuid}")
        return {
            "status": "success",
            "capture_uuid": capture_uuid,
            "message": "Waterfall JSON data processed and stored successfully",
            "json_data": waterfall_result["json_data"],
            "metadata": waterfall_result["metadata"],
            "store_result": store_result,
        }

    except Exception as e:
        logger.error(f"Waterfall processing failed for capture {capture_uuid}: {e}")
        raise


@cog
def update_processing_status_cog(
    capture_uuid: str, processing_type: str, status: str, step: str | None = None
) -> dict[str, Any]:
    """Update the processing status for a specific processing type.

    Args:
        capture_uuid: UUID of the capture
        processing_type: Type of processing
        status: Status to set (processing, completed, failed)
        step: Optional step name for processing status

    Returns:
        Dict with status update info
    """
    try:
        # Import models here to avoid Django app registry issues
        from .models import Capture
        from .models import PostProcessedData

        capture = Capture.objects.get(uuid=capture_uuid)
        processed_data = PostProcessedData.objects.filter(
            capture=capture,
            processing_type=processing_type,
        ).first()

        if processed_data:
            if status == "processing":
                processed_data.mark_processing_started(
                    pipeline_id="django_cog_pipeline", step=step or "processing"
                )
            elif status == "completed":
                processed_data.mark_processing_completed()
            elif status == "failed":
                processed_data.mark_processing_failed(f"Pipeline step failed: {step}")

        return {
            "status": "success",
            "capture_uuid": capture_uuid,
            "processing_type": processing_type,
            "status": status,
        }
    except Exception as e:
        logger.error(f"Failed to update processing status: {e}")
        raise


@cog
def setup_post_processing_cog(
    capture_uuid: str, processing_types: list[str] | None = None
) -> dict[str, Any]:
    """Setup post-processing for a capture.

    Args:
        capture_uuid: UUID of the capture to process
        processing_types: List of processing types to run

    Returns:
        Dict with status and setup info
    """
    try:
        logger.info(f"Starting setup for capture {capture_uuid}")

        # Import models here to avoid Django app registry issues
        from .models import Capture
        from .models import CaptureType
        from .models import ProcessingType
        from .tasks import _create_or_reset_processed_data

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
                    import time

                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    # Final attempt failed
                    error_msg = (
                        f"Capture {capture_uuid} not found after {max_retries} attempts"
                    )
                    logger.error(error_msg)
                    raise ValueError(error_msg)

        # At this point, capture should not be None due to the retry logic above
        assert capture is not None, (
            f"Capture {capture_uuid} should have been found by now"
        )

        # Validate capture type
        if capture.capture_type != CaptureType.DigitalRF:
            raise ValueError(f"Capture {capture_uuid} is not a DigitalRF capture")

        # Set default processing types if not specified
        if not processing_types:
            processing_types = [ProcessingType.Waterfall.value]

        # Create PostProcessedData records for each processing type
        for processing_type in processing_types:
            _create_or_reset_processed_data(capture, processing_type)

        logger.info(f"Completed setup for capture {capture_uuid}")
        return {
            "status": "success",
            "capture_uuid": capture_uuid,
            "processing_types": processing_types,
            "capture_type": capture.capture_type.value,
            "channel": capture.channel,
        }
    except Exception as e:
        logger.error(f"Setup failed for capture {capture_uuid}: {e}")
        raise


# Pipeline configuration functions for Django admin setup
def get_waterfall_pipeline_config() -> dict[str, Any]:
    """Get configuration for waterfall processing pipeline.

    This should be used to set up the pipeline in Django admin with the following structure:

    Pipeline:
    - Name: "Waterfall Processing"
    - Schedule: None (manual launch)

    Stages:
    1. "setup_stage" - setup_post_processing_cog (validates capture, creates records)
    2. "process_stage" - process_waterfall_data_cog (does download, processing, and storage)

    Tasks in each stage:
    - setup_stage: setup_post_processing_cog (capture_uuid and processing_types passed as runtime args)
    - process_stage: process_waterfall_data_cog (capture_uuid passed as runtime arg, depends on setup_stage)
    """
    return {
        "pipeline_name": "Waterfall Processing",
        "stages": [
            {
                "name": "setup_stage",
                "description": "Setup post-processing (validate capture, create records)",
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
                "name": "process_stage",
                "description": "Process waterfall data (downloads, processes, and stores)",
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
        ],
    }


# Pipeline registry for easy access
PIPELINE_CONFIGS = {
    "waterfall": get_waterfall_pipeline_config,  # Simplified single-step pipeline
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
        raise ValueError(f"Unknown pipeline type: {pipeline_type}")

    return config_func()
