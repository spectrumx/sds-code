"""Django-cog pipeline configurations for visualization processing."""

import json
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any

from django_cog import cog
from django_cog import cog_error_handler
from loguru import logger

from sds_gateway.visualizations.errors import ConfigurationError
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
                "name": "processing_stage",
                "description": "Process visualization data (downloads, processes, and "
                "stores)",
                "depends_on": ["setup_stage"],
                "tasks": [
                    {
                        "name": "process_waterfall",
                        "cog": "process_waterfall_data_cog",
                        "args": {},
                        "description": "Process waterfall data",
                    },
                    {
                        "name": "process_spectrogram",
                        "cog": "process_spectrogram_data_cog",
                        "args": {},
                        "description": "Process spectrogram data",
                    },
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
        raise ConfigurationError(error_msg)

    return config_func()


# Cog functions (pipeline steps)
@cog
def setup_post_processing_cog(
    capture_uuid: str, processing_config: dict[str, dict[str, Any]]
) -> None:
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

    try:
        logger.info(
            f"Starting setup for capture {capture_uuid} with config: "
            f"{processing_config}"
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
            raise ConfigurationError(error_msg)  # noqa: TRY301

        # Validate processing config
        if not processing_config:
            error_msg = "No processing config specified"
            raise ConfigurationError(error_msg)  # noqa: TRY301

        # PostProcessedData records should be created before the pipeline starts
        # This function just validates the capture and config
        logger.info(
            f"Processing config received for {len(processing_config)} processing types"
        )
        for processing_type, parameters in processing_config.items():
            logger.info(
                f"Processing type {processing_type} with parameters: {parameters}"
            )

            # Validate that processed_data_id is provided
            processed_data_id = parameters.get("processed_data_id")
            if not processed_data_id:
                error_msg = (
                    f"processed_data_id is required for {processing_type} processing. "
                    f"PostProcessedData records must be created before starting the "
                    f"pipeline."
                )
                raise ConfigurationError(error_msg)  # noqa: TRY301

        logger.info(f"Completed setup for capture {capture_uuid}")
    except Exception as e:
        logger.error(f"Setup failed for capture {capture_uuid}: {e}")
        raise


def _process_waterfall_json_data(capture, processed_data_obj, temp_path):
    """Process waterfall JSON data and return result."""
    from sds_gateway.visualizations.processing.utils import (  # noqa: PLC0415
        reconstruct_drf_files,
    )

    capture_files = capture.files.filter(is_deleted=False)
    reconstructed_path = reconstruct_drf_files(capture, capture_files, temp_path)

    waterfall_result = convert_drf_to_waterfall_json(
        reconstructed_path,
        capture.channel,
        max_slices=500000,
    )

    return waterfall_result


def _store_waterfall_json_file(capture_uuid, waterfall_result):
    """Store waterfall JSON file and return result."""
    from sds_gateway.visualizations.models import ProcessingType  # noqa: PLC0415
    from sds_gateway.visualizations.processing.utils import (  # noqa: PLC0415
        store_processed_data,
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as temp_file:
        json.dump(waterfall_result["json_data"], temp_file, indent=2)
        temp_file_path = temp_file.name
        logger.info(f"Created temporary JSON file at {temp_file_path}")

    try:
        new_filename = f"waterfall_{capture_uuid}.json"
        store_processed_data(
            capture_uuid,
            ProcessingType.Waterfall.value,
            temp_file_path,
            new_filename,
            waterfall_result["metadata"],
        )

        return temp_file_path  # noqa: TRY300
    except Exception:
        if temp_file_path:
            Path(temp_file_path).unlink(missing_ok=True)
        raise


@cog
def process_waterfall_data_cog(
    capture_uuid: str,
    processing_config: dict[str, dict[str, Any]],
) -> None:
    """Process waterfall data for a capture.

    Args:
        capture_uuid: UUID of the capture to process
        processing_config: Dict with processing configurations

    Returns:
        None
    """
    processing_types = list(processing_config.keys()) if processing_config else []
    if "waterfall" not in processing_types:
        logger.info(
            f"Skipping waterfall processing for capture {capture_uuid} - not requested"
        )
        return

    logger.info(f"Processing waterfall JSON data for capture {capture_uuid}")

    from sds_gateway.api_methods.models import Capture  # noqa: PLC0415
    from sds_gateway.visualizations.models import PostProcessedData  # noqa: PLC0415
    from sds_gateway.visualizations.models import ProcessingType  # noqa: PLC0415

    capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)

    # Get the processed data record using the ID from processing config
    waterfall_config = processing_config.get("waterfall", {})
    processed_data_id = waterfall_config.get("processed_data_id")

    if not processed_data_id:
        error_msg = (
            "processed_data_id is required for waterfall processing. "
            "PostProcessedData records must be created before starting the pipeline."
        )
        raise ValueError(error_msg)

    # Use the specific PostProcessedData ID
    try:
        processed_data_obj = PostProcessedData.objects.get(
            uuid=processed_data_id,
            capture=capture,
            processing_type=ProcessingType.Waterfall.value,
        )
    except PostProcessedData.DoesNotExist:
        error_msg = f"PostProcessedData with ID {processed_data_id} not found"
        raise ValueError(error_msg) from None
    processed_data_obj.mark_processing_started(pipeline_id="django_cog_pipeline")

    with tempfile.TemporaryDirectory(prefix=f"waterfall_{capture_uuid}_") as temp_dir:
        temp_path = Path(temp_dir)
        temp_file_path = None
        try:
            waterfall_result = _process_waterfall_json_data(
                capture, processed_data_obj, temp_path
            )
            temp_file_path = _store_waterfall_json_file(capture_uuid, waterfall_result)

            processed_data_obj.mark_processing_completed()
            logger.info(f"Completed waterfall processing for capture {capture_uuid}")

        finally:
            if temp_file_path:
                Path(temp_file_path).unlink(missing_ok=True)
                logger.info(f"Cleaned up temporary file {temp_file_path}")


@cog
def process_spectrogram_data_cog(
    capture_uuid: str, processing_config: dict[str, dict[str, Any]]
) -> None:
    """Process spectrogram data for a capture.

    Args:
        capture_uuid: UUID of the capture to process
        processing_config: Dict with processing configurations

    Returns:
        None
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
        return

    logger.info(f"Processing spectrogram data for capture {capture_uuid}")

    capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)

    # Get the processed data record using the ID from processing config
    spectrogram_config = processing_config.get("spectrogram", {})
    processed_data_id = spectrogram_config.get("processed_data_id")

    if not processed_data_id:
        error_msg = (
            "processed_data_id is required for spectrogram processing. "
            "PostProcessedData records must be created before starting the pipeline."
        )
        raise ValueError(error_msg)

    # Use the specific PostProcessedData ID
    try:
        processed_data_obj = PostProcessedData.objects.get(
            uuid=processed_data_id,
            capture=capture,
            processing_type=ProcessingType.Spectrogram.value,
        )
    except PostProcessedData.DoesNotExist:
        error_msg = f"PostProcessedData with ID {processed_data_id} not found"
        raise ValueError(error_msg) from None
    # Mark processing as started
    processed_data_obj.mark_processing_started(pipeline_id="django_cog_pipeline")

    # Use built-in temporary directory context manager
    with tempfile.TemporaryDirectory(prefix=f"spectrogram_{capture_uuid}_") as temp_dir:
        temp_path = Path(temp_dir)

        # Reconstruct the DigitalRF files for processing
        from sds_gateway.visualizations.processing.utils import (  # noqa: PLC0415
            reconstruct_drf_files,
        )

        capture_files = capture.files.filter(is_deleted=False)
        reconstructed_path = reconstruct_drf_files(capture, capture_files, temp_path)

        # Generate spectrogram
        from sds_gateway.visualizations.processing.spectrogram import (  # noqa: PLC0415
            generate_spectrogram_from_drf,
        )

        spectrogram_result = generate_spectrogram_from_drf(
            reconstructed_path,
            capture.channel,
            processing_config["spectrogram"],
        )

        # Store the spectrogram image
        from sds_gateway.visualizations.processing.utils import (  # noqa: PLC0415
            store_processed_data,
        )

        store_processed_data(
            capture_uuid,
            ProcessingType.Spectrogram.value,
            spectrogram_result["image_path"],
            f"spectrogram_{capture_uuid}.png",
            spectrogram_result["metadata"],
        )

        # Mark processing as completed
        processed_data_obj.mark_processing_completed()

        logger.info(f"Completed spectrogram processing for capture {capture_uuid}")


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
    logger.opt(exception=error).error(f"Failed task: {error}")

    if task_run:
        logger.warning(f"Failed task: {task_run.task.name}")
        logger.warning(f"Task run ID: {task_run.id}")

        # Try to extract capture_uuid from pipeline run arguments
        try:
            # Get the pipeline run arguments through the task run -> stage run ->
            # pipeline run chain
            pipeline_run = task_run.stage_run.pipeline_run
            pipeline_args_raw = pipeline_run.arguments_as_json or {}

            # Handle case where arguments_as_json might be a string
            if isinstance(pipeline_args_raw, str):
                pipeline_args = json.loads(pipeline_args_raw)
            else:
                pipeline_args = pipeline_args_raw

            capture_uuid = pipeline_args.get("capture_uuid")
            if capture_uuid:
                logger.info(
                    f"Marking PostProcessedData records as failed for "
                    f"capture {capture_uuid}"
                )

                # Import models here to avoid Django app registry issues
                from sds_gateway.visualizations.models import (  # noqa: PLC0415
                    PostProcessedData,
                )
                from sds_gateway.visualizations.models import (  # noqa: PLC0415
                    ProcessingStatus,
                )

                # Find any PostProcessedData records for this capture that are pending
                # or processing
                failed_records = PostProcessedData.objects.filter(
                    capture__uuid=capture_uuid,
                    processing_status__in=[
                        ProcessingStatus.Pending.value,
                        ProcessingStatus.Processing.value,
                    ],
                )

                if not failed_records:
                    logger.warning(
                        f"No PostProcessedData records found for capture {capture_uuid}"
                        f" that are pending or processing"
                    )
                    return

                for record in failed_records:
                    # Create a CogError record for detailed error tracking
                    from django_cog.models import CogError  # noqa: PLC0415

                    error_type = type(error).__name__
                    error_info = "".join(
                        traceback.format_exception(
                            type(error), value=error, tb=error.__traceback__
                        )
                    )
                    cog_error = CogError.objects.create(
                        task_run=task_run, traceback=error_info, error_type=error_type
                    )

                    # For COG errors, we only store the CogError reference
                    # The processing_error field remains empty for COG errors
                    record.mark_processing_failed(None, cog_error)
                    logger.warning(
                        f"Marked PostProcessedData record {record.uuid} as failed "
                        f"due to COG task failure ({error_type}) - "
                        f"CogError ID: {cog_error.id}"
                    )

            else:
                logger.error(
                    "Could not extract capture_uuid from pipeline run arguments"
                )

        except (ValueError, KeyError, AttributeError) as cleanup_error:
            logger.error(f"Failed to update PostProcessedData records: {cleanup_error}")
    else:
        logger.warning("No task_run object provided to error handler")
