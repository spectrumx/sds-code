"""Post-processing launch functions for visualizations."""

from typing import Any

from loguru import logger

from sds_gateway.api_methods.models import Capture
from sds_gateway.visualizations.errors import ConfigurationError
from sds_gateway.visualizations.models import PostProcessedData
from sds_gateway.visualizations.models import ProcessingStatus
from sds_gateway.visualizations.models import ProcessingType


def launch_visualization_processing(
    capture_uuid: str, processing_config: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """
    Launch visualization processing for a DigitalRF capture.

    This function creates PostProcessedData records for each processing type
    and then launches the django-cog pipeline with the record IDs.

    Args:
        capture_uuid: UUID of the capture to process
        processing_config: Dict with processing configurations, e.g.:
            {
                "spectrogram": {"fft_size": 1024, "std_dev": 100, "hop_size": 500,
                "colormap": "magma"}, "waterfall": {...}
            }

    Returns:
        dict: Result with status and details
    """
    logger.info(f"Launching visualization processing for capture {capture_uuid}")

    try:
        # Validate processing config
        if not processing_config:
            error_msg = "No processing config specified"
            raise ConfigurationError(error_msg)  # noqa: TRY301

        # Get the capture
        capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)

        # Get the appropriate pipeline from the database
        from sds_gateway.visualizations.models import (  # noqa: PLC0415
            get_latest_pipeline_by_base_name,
        )

        # Always use the visualization pipeline - individual cogs will check if they
        # should run
        pipeline_name = "visualization_processing"
        pipeline = get_latest_pipeline_by_base_name(pipeline_name)
        if not pipeline:
            error_msg = (
                f"No {pipeline_name} pipeline found. Please run setup_pipelines."
            )
            raise ConfigurationError(error_msg)  # noqa: TRY301

        # Create PostProcessedData records for each processing type
        logger.info(
            f"Creating PostProcessedData records for {len(processing_config)} "
            f"processing types"
        )

        updated_processing_config = {}
        for processing_type, parameters in processing_config.items():
            # Check if processed_data_id already exists
            existing_processed_data_id = parameters.get("processed_data_id")
            if existing_processed_data_id:
                # Use existing processed_data_id
                logger.info(
                    f"Using existing processed_data with ID "
                    f"{existing_processed_data_id} for {processing_type}"
                )
                updated_processing_config[processing_type] = parameters
            else:
                # Create PostProcessedData record
                processed_data = PostProcessedData.objects.create(
                    capture=capture,
                    processing_type=ProcessingType(processing_type).value,
                    processing_parameters=parameters,
                    processing_status=ProcessingStatus.Pending.value,
                    metadata={},
                    pipeline_id=pipeline.name,
                )

                # Add processed_data_id to the config
                updated_processing_config[processing_type] = {
                    **parameters,
                    "processed_data_id": str(processed_data.uuid),
                }

                logger.info(
                    f"Created PostProcessedData record {processed_data.uuid} "
                    f"for {processing_type}"
                )

        # Launch the visualization pipeline with updated processing config
        logger.info(
            f"Launching pipeline {pipeline_name} for capture {capture_uuid} "
            f"with config: {updated_processing_config}"
        )
        pipeline.launch(
            capture_uuid=capture_uuid, processing_config=updated_processing_config
        )
        logger.info(f"Pipeline launched successfully for capture {capture_uuid}")

        return {
            "processing_config": updated_processing_config,
        }
    except Exception as e:
        error_msg = f"Unexpected error in visualization processing: {e}"
        logger.exception(error_msg)
        raise
