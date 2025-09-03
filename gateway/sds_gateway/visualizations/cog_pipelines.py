"""Django-cog pipeline configurations for visualization processing."""

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from django_cog import cog
from django_cog import cog_error_handler
from loguru import logger

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
        "error_handler": "visualization_error_handler",
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
def setup_post_processing_cog(capture_uuid: str, processing_config: dict) -> None:
    """Setup post-processing for a capture.

    Args:
        capture_uuid: UUID of the capture to process
        processing_config: Dict with processing configurations for each type
    Returns:
        None
    """

    # imports to run when the app is ready
    from sds_gateway.api_methods.models import Capture  # noqa: PLC0415
    from sds_gateway.api_methods.models import CaptureType  # noqa: PLC0415
    from sds_gateway.visualizations.models import ProcessingType  # noqa: PLC0415
    from sds_gateway.visualizations.processing.utils import (  # noqa: PLC0415
        create_or_reset_processed_data,
    )

    try:
        logger.info(
            f"Starting setup for capture {capture_uuid} with config: {processing_config}"
        )

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

        # Validate processing config
        if not processing_config:
            error_msg = "No processing config specified"
            raise ValueError(error_msg)  # noqa: TRY301

        # Create PostProcessedData records for each processing type
        logger.info(
            f"Creating PostProcessedData records for {len(processing_config)} processing types"
        )
        for processing_type, parameters in processing_config.items():
            logger.info(
                f"Creating record for {processing_type} with parameters: {parameters}"
            )
            create_or_reset_processed_data(
                capture, ProcessingType(processing_type), parameters
            )

        logger.info(f"Completed setup for capture {capture_uuid}")
    except Exception as e:
        logger.error(f"Setup failed for capture {capture_uuid}: {e}")
        raise


@cog
def process_waterfall_data_cog(
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
    if processing_types and ProcessingType.Waterfall.value not in processing_types:
        logger.info(
            f"Skipping waterfall processing for capture {capture_uuid} - not requested"
        )
        return {
            "status": "skipped",
            "message": "Waterfall processing not requested",
            "capture_uuid": capture_uuid,
        }

    logger.info(f"Processing waterfall JSON data for capture {capture_uuid}")

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
        raise ValueError(error_msg)

    # Mark processing as started
    processed_data.mark_processing_started(pipeline_id="django_cog_pipeline")

    # Use built-in temporary directory context manager
    with tempfile.TemporaryDirectory(prefix=f"waterfall_{capture_uuid}_") as temp_dir:
        temp_path = Path(temp_dir)

        # Reconstruct the DigitalRF files for processing
        capture_files = capture.files.filter(is_deleted=False)
        reconstructed_path = reconstruct_drf_files(capture, capture_files, temp_path)

        if not reconstructed_path:
            error_msg = "Failed to reconstruct DigitalRF directory structure"
            processed_data.mark_processing_failed(error_msg)
            raise ValueError(error_msg)

        # Process the waterfall data in JSON format
        waterfall_result = convert_drf_to_waterfall_json(
            reconstructed_path,
            capture.channel,
        )

        if waterfall_result["status"] != "success":
            processed_data.mark_processing_failed(waterfall_result["message"])
            raise ValueError(waterfall_result["message"])

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

            logger.info(f"Completed waterfall processing for capture {capture_uuid}")
            return {
                "status": "success",
                "capture_uuid": capture_uuid,
                "message": ("Waterfall JSON data processed and stored successfully"),
                "json_data": waterfall_result["json_data"],
                "metadata": waterfall_result["metadata"],
                "store_result": store_result,
            }

        finally:
            # Clean up temporary file
            if "temp_file_path" in locals():
                Path(temp_file_path).unlink(missing_ok=True)
                logger.info(f"Cleaned up temporary file {temp_file_path}")


@cog
def process_spectrogram_data_cog(
    capture_uuid: str, processing_config: dict
) -> dict[str, Any]:
    """Process spectrogram data for a capture.

    Args:
        capture_uuid: UUID of the capture to process
        processing_config: Dict with processing configurations

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

    # Check if spectrogram processing is requested
    if ProcessingType.Spectrogram.value not in processing_config:
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
        raise ValueError(error_msg)

    # Mark processing as started
    processed_data.mark_processing_started(pipeline_id="django_cog_pipeline")

    # Use built-in temporary directory context manager
    with tempfile.TemporaryDirectory(prefix=f"spectrogram_{capture_uuid}_") as temp_dir:
        temp_path = Path(temp_dir)

        # Reconstruct the DigitalRF files for processing
        from sds_gateway.visualizations.processing.utils import reconstruct_drf_files

        capture_files = capture.files.filter(is_deleted=False)
        reconstructed_path = reconstruct_drf_files(capture, capture_files, temp_path)

        if not reconstructed_path:
            error_msg = "Failed to reconstruct DigitalRF directory structure"
            processed_data.mark_processing_failed(error_msg)
            raise ValueError(error_msg)

        # Generate spectrogram
        from sds_gateway.visualizations.processing.spectrogram import (
            generate_spectrogram_from_drf,
        )

        spectrogram_result = generate_spectrogram_from_drf(
            reconstructed_path,
            capture.channel,
            processing_config["spectrogram"],
        )

        if spectrogram_result["status"] != "success":
            processed_data.mark_processing_failed(spectrogram_result["message"])
            raise ValueError(spectrogram_result["message"])

        # Store the spectrogram image
        from sds_gateway.visualizations.processing.utils import store_processed_data

        store_result = store_processed_data(
            capture_uuid,
            ProcessingType.Spectrogram.value,
            spectrogram_result["image_path"],
            f"spectrogram_{capture_uuid}.png",
            spectrogram_result["metadata"],
        )

        if store_result["status"] != "success":
            processed_data.mark_processing_failed(store_result["message"])
            raise ValueError(store_result["message"])

        # Mark processing as completed
        processed_data.mark_processing_completed()

        logger.info(f"Completed spectrogram processing for capture {capture_uuid}")
        return {
            "status": "success",
            "capture_uuid": capture_uuid,
            "message": "Spectrogram processed and stored successfully",
            "metadata": spectrogram_result["metadata"],
            "store_result": store_result,
        }


# Custom error handler for COG tasks
@cog_error_handler
def visualization_error_handler(error, task_run=None):
    """
    Custom error handler for visualization pipeline tasks.

    This handler automatically updates PostProcessedData records to "failed" status
    when any COG task fails, providing centralized error handling.

    Args:
        error: The exception that occurred
        task_run: The task run object (optional, provided by Django COG)
    """
    logger.error(f"COG task failed: {error}")

    if task_run:
        logger.error(f"Failed task: {task_run.task.name}")
        logger.error(f"Task run ID: {task_run.id}")

        # Try to extract capture_uuid from task arguments
        try:
            # Get the task arguments - they should contain capture_uuid
            task_args = task_run.task.arguments_as_json or {}
            capture_uuid = task_args.get("capture_uuid")

            if capture_uuid:
                logger.info(
                    f"Attempting to mark PostProcessedData records as failed for capture {capture_uuid}"
                )

                # Import models here to avoid Django app registry issues
                from sds_gateway.visualizations.models import PostProcessedData
                from sds_gateway.visualizations.models import ProcessingStatus

                # Find any PostProcessedData records for this capture that are still pending
                failed_records = PostProcessedData.objects.filter(
                    capture__uuid=capture_uuid,
                    processing_status=ProcessingStatus.Pending.value,
                )

                for record in failed_records:
                    error_message = f"COG task '{task_run.task.name}' failed: {error}"
                    record.mark_processing_failed(error_message)
                    logger.info(
                        f"Marked PostProcessedData record {record.uuid} as failed due to COG task failure"
                    )

            else:
                logger.warning("Could not extract capture_uuid from task arguments")

        except Exception as cleanup_error:
            logger.error(f"Failed to update PostProcessedData records: {cleanup_error}")
    else:
        logger.warning("No task_run object provided to error handler")
