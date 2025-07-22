"""Django-cog pipeline configurations for post-processing."""

from typing import Any

from django_cog import cog
from loguru import logger

from .models import Capture
from .models import PostProcessedData
from .tasks import cleanup_temp_files
from .tasks import download_capture_files
from .tasks import process_spectrogram_data
from .tasks import process_waterfall_data
from .tasks import store_processed_data


@cog
def download_capture_files_cog(capture_uuid: str) -> dict[str, Any]:
    """Download DigitalRF files from storage.

    Args:
        capture_uuid: UUID of the capture to process

    Returns:
        Dict with status and any relevant data
    """
    try:
        logger.info(f"Starting download for capture {capture_uuid}")
        result = download_capture_files(capture_uuid)
        logger.info(f"Completed download for capture {capture_uuid}")
        return {"status": "success", "capture_uuid": capture_uuid, "result": result}
    except Exception as e:
        logger.error(f"Download failed for capture {capture_uuid}: {e}")
        raise


@cog
def process_waterfall_data_cog(capture_uuid: str) -> dict[str, Any]:
    """Process waterfall data for a capture.

    Args:
        capture_uuid: UUID of the capture to process

    Returns:
        Dict with status and processed data info
    """
    try:
        logger.info(f"Starting waterfall processing for capture {capture_uuid}")
        result = process_waterfall_data(capture_uuid)
        logger.info(f"Completed waterfall processing for capture {capture_uuid}")
        return {"status": "success", "capture_uuid": capture_uuid, "result": result}
    except Exception as e:
        logger.error(f"Waterfall processing failed for capture {capture_uuid}: {e}")
        raise


@cog
def process_spectrogram_data_cog(capture_uuid: str) -> dict[str, Any]:
    """Process spectrogram data for a capture.

    Args:
        capture_uuid: UUID of the capture to process

    Returns:
        Dict with status and processed data info
    """
    try:
        logger.info(f"Starting spectrogram processing for capture {capture_uuid}")
        result = process_spectrogram_data(capture_uuid)
        logger.info(f"Completed spectrogram processing for capture {capture_uuid}")
        return {"status": "success", "capture_uuid": capture_uuid, "result": result}
    except Exception as e:
        logger.error(f"Spectrogram processing failed for capture {capture_uuid}: {e}")
        raise


@cog
def store_processed_data_cog(capture_uuid: str, processing_type: str) -> dict[str, Any]:
    """Store processed data for a capture.

    Args:
        capture_uuid: UUID of the capture
        processing_type: Type of processing (waterfall, spectrogram, etc.)

    Returns:
        Dict with status and storage info
    """
    try:
        logger.info(
            f"Starting storage for {processing_type} data, capture {capture_uuid}"
        )
        result = store_processed_data(capture_uuid, processing_type)
        logger.info(
            f"Completed storage for {processing_type} data, capture {capture_uuid}"
        )
        return {
            "status": "success",
            "capture_uuid": capture_uuid,
            "processing_type": processing_type,
            "result": result,
        }
    except Exception as e:
        logger.error(
            f"Storage failed for {processing_type} data, capture {capture_uuid}: {e}"
        )
        raise


@cog
def cleanup_temp_files_cog(capture_uuid: str) -> dict[str, Any]:
    """Clean up temporary files for a capture.

    Args:
        capture_uuid: UUID of the capture

    Returns:
        Dict with status and cleanup info
    """
    try:
        logger.info(f"Starting cleanup for capture {capture_uuid}")
        result = cleanup_temp_files(capture_uuid)
        logger.info(f"Completed cleanup for capture {capture_uuid}")
        return {"status": "success", "capture_uuid": capture_uuid, "result": result}
    except Exception as e:
        logger.error(f"Cleanup failed for capture {capture_uuid}: {e}")
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


# Pipeline configuration functions for Django admin setup
def get_waterfall_pipeline_config() -> dict[str, Any]:
    """Get configuration for waterfall processing pipeline.

    This should be used to set up the pipeline in Django admin with the following structure:

    Pipeline:
    - Name: "Waterfall Processing"
    - Schedule: None (manual launch)

    Stages:
    1. "download_stage" - download_capture_files_cog
    2. "process_stage" - process_waterfall_data_cog (depends on download_stage)
    3. "store_stage" - store_processed_data_cog (depends on process_stage)
    4. "cleanup_stage" - cleanup_temp_files_cog (depends on store_stage)

    Tasks in each stage:
    - download_stage: download_capture_files_cog with args: {"capture_uuid": "{{capture_uuid}}"}
    - process_stage: process_waterfall_data_cog with args: {"capture_uuid": "{{capture_uuid}}"}
    - store_stage: store_processed_data_cog with args: {"capture_uuid": "{{capture_uuid}}", "processing_type": "waterfall"}
    - cleanup_stage: cleanup_temp_files_cog with args: {"capture_uuid": "{{capture_uuid}}"}
    """
    return {
        "pipeline_name": "Waterfall Processing",
        "stages": [
            {
                "name": "download_stage",
                "description": "Download DigitalRF files from storage",
                "tasks": [
                    {
                        "name": "download_files",
                        "cog": "download_capture_files_cog",
                        "args": {"capture_uuid": "{{capture_uuid}}"},
                        "description": "Download capture files",
                    }
                ],
            },
            {
                "name": "process_stage",
                "description": "Process waterfall data",
                "depends_on": ["download_stage"],
                "tasks": [
                    {
                        "name": "process_waterfall",
                        "cog": "process_waterfall_data_cog",
                        "args": {"capture_uuid": "{{capture_uuid}}"},
                        "description": "Process waterfall data",
                    }
                ],
            },
            {
                "name": "store_stage",
                "description": "Store processed waterfall data",
                "depends_on": ["process_stage"],
                "tasks": [
                    {
                        "name": "store_waterfall",
                        "cog": "store_processed_data_cog",
                        "args": {
                            "capture_uuid": "{{capture_uuid}}",
                            "processing_type": "waterfall",
                        },
                        "description": "Store waterfall data",
                    }
                ],
            },
            {
                "name": "cleanup_stage",
                "description": "Clean up temporary files",
                "depends_on": ["store_stage"],
                "tasks": [
                    {
                        "name": "cleanup_files",
                        "cog": "cleanup_temp_files_cog",
                        "args": {"capture_uuid": "{{capture_uuid}}"},
                        "description": "Clean up temporary files",
                    }
                ],
            },
        ],
    }


def get_spectrogram_pipeline_config() -> dict[str, Any]:
    """Get configuration for spectrogram processing pipeline.

    This should be used to set up the pipeline in Django admin with the following structure:

    Pipeline:
    - Name: "Spectrogram Processing"
    - Schedule: None (manual launch)

    Stages:
    1. "download_stage" - download_capture_files_cog
    2. "process_stage" - process_spectrogram_data_cog (depends on download_stage)
    3. "store_stage" - store_processed_data_cog (depends on process_stage)
    4. "cleanup_stage" - cleanup_temp_files_cog (depends on store_stage)

    Tasks in each stage:
    - download_stage: download_capture_files_cog with args: {"capture_uuid": "{{capture_uuid}}"}
    - process_stage: process_spectrogram_data_cog with args: {"capture_uuid": "{{capture_uuid}}"}
    - store_stage: store_processed_data_cog with args: {"capture_uuid": "{{capture_uuid}}", "processing_type": "spectrogram"}
    - cleanup_stage: cleanup_temp_files_cog with args: {"capture_uuid": "{{capture_uuid}}"}
    """
    return {
        "pipeline_name": "Spectrogram Processing",
        "stages": [
            {
                "name": "download_stage",
                "description": "Download DigitalRF files from storage",
                "tasks": [
                    {
                        "name": "download_files",
                        "cog": "download_capture_files_cog",
                        "args": {"capture_uuid": "{{capture_uuid}}"},
                        "description": "Download capture files",
                    }
                ],
            },
            {
                "name": "process_stage",
                "description": "Process spectrogram data",
                "depends_on": ["download_stage"],
                "tasks": [
                    {
                        "name": "process_spectrogram",
                        "cog": "process_spectrogram_data_cog",
                        "args": {"capture_uuid": "{{capture_uuid}}"},
                        "description": "Process spectrogram data",
                    }
                ],
            },
            {
                "name": "store_stage",
                "description": "Store processed spectrogram data",
                "depends_on": ["process_stage"],
                "tasks": [
                    {
                        "name": "store_spectrogram",
                        "cog": "store_processed_data_cog",
                        "args": {
                            "capture_uuid": "{{capture_uuid}}",
                            "processing_type": "spectrogram",
                        },
                        "description": "Store spectrogram data",
                    }
                ],
            },
            {
                "name": "cleanup_stage",
                "description": "Clean up temporary files",
                "depends_on": ["store_stage"],
                "tasks": [
                    {
                        "name": "cleanup_files",
                        "cog": "cleanup_temp_files_cog",
                        "args": {"capture_uuid": "{{capture_uuid}}"},
                        "description": "Clean up temporary files",
                    }
                ],
            },
        ],
    }


def get_multi_processing_pipeline_config() -> dict[str, Any]:
    """Get configuration for multi-processing pipeline (waterfall + spectrogram).

    This should be used to set up the pipeline in Django admin with the following structure:

    Pipeline:
    - Name: "Multi-Processing Pipeline"
    - Schedule: None (manual launch)

    Stages:
    1. "download_stage" - download_capture_files_cog
    2. "process_stage" - parallel processing of waterfall and spectrogram (depends on download_stage)
    3. "store_stage" - parallel storage of waterfall and spectrogram data (depends on process_stage)
    4. "cleanup_stage" - cleanup_temp_files_cog (depends on store_stage)

    Tasks in each stage:
    - download_stage: download_capture_files_cog with args: {"capture_uuid": "{{capture_uuid}}"}
    - process_stage:
      * process_waterfall_data_cog with args: {"capture_uuid": "{{capture_uuid}}"}
      * process_spectrogram_data_cog with args: {"capture_uuid": "{{capture_uuid}}"}
    - store_stage:
      * store_processed_data_cog with args: {"capture_uuid": "{{capture_uuid}}", "processing_type": "waterfall"}
      * store_processed_data_cog with args: {"capture_uuid": "{{capture_uuid}}", "processing_type": "spectrogram"}
    - cleanup_stage: cleanup_temp_files_cog with args: {"capture_uuid": "{{capture_uuid}}"}
    """
    return {
        "pipeline_name": "Multi-Processing Pipeline",
        "stages": [
            {
                "name": "download_stage",
                "description": "Download DigitalRF files from storage",
                "tasks": [
                    {
                        "name": "download_files",
                        "cog": "download_capture_files_cog",
                        "args": {"capture_uuid": "{{capture_uuid}}"},
                        "description": "Download capture files",
                    }
                ],
            },
            {
                "name": "process_stage",
                "description": "Process waterfall and spectrogram data in parallel",
                "depends_on": ["download_stage"],
                "tasks": [
                    {
                        "name": "process_waterfall",
                        "cog": "process_waterfall_data_cog",
                        "args": {"capture_uuid": "{{capture_uuid}}"},
                        "description": "Process waterfall data",
                    },
                    {
                        "name": "process_spectrogram",
                        "cog": "process_spectrogram_data_cog",
                        "args": {"capture_uuid": "{{capture_uuid}}"},
                        "description": "Process spectrogram data",
                    },
                ],
            },
            {
                "name": "store_stage",
                "description": "Store processed waterfall and spectrogram data in parallel",
                "depends_on": ["process_stage"],
                "tasks": [
                    {
                        "name": "store_waterfall",
                        "cog": "store_processed_data_cog",
                        "args": {
                            "capture_uuid": "{{capture_uuid}}",
                            "processing_type": "waterfall",
                        },
                        "description": "Store waterfall data",
                    },
                    {
                        "name": "store_spectrogram",
                        "cog": "store_processed_data_cog",
                        "args": {
                            "capture_uuid": "{{capture_uuid}}",
                            "processing_type": "spectrogram",
                        },
                        "description": "Store spectrogram data",
                    },
                ],
            },
            {
                "name": "cleanup_stage",
                "description": "Clean up temporary files",
                "depends_on": ["store_stage"],
                "tasks": [
                    {
                        "name": "cleanup_files",
                        "cog": "cleanup_temp_files_cog",
                        "args": {"capture_uuid": "{{capture_uuid}}"},
                        "description": "Clean up temporary files",
                    }
                ],
            },
        ],
    }


# Pipeline registry for easy access
PIPELINE_CONFIGS = {
    "waterfall": get_waterfall_pipeline_config,
    "spectrogram": get_spectrogram_pipeline_config,
    "multi_processing": get_multi_processing_pipeline_config,
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
