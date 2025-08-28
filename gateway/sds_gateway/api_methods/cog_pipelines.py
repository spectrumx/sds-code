"""Django-cog pipeline configurations for post-processing."""

import base64
import datetime
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from digital_rf import DigitalRFReader
from django.conf import settings
from django_cog import cog
from loguru import logger

# PLC0415: models are imported in functions to run after the Django app is ready
# ruff: noqa: PLC0415


@dataclass
class WaterfallSliceParams:
    """Parameters for processing a waterfall slice."""

    reader: Any
    channel: str
    slice_idx: int
    start_sample: int
    samples_per_slice: int
    end_sample: int
    fft_size: int
    min_frequency: float
    max_frequency: float
    sample_rate: float
    center_freq: float


# Pipeline configuration functions for Django admin setup
def get_waterfall_pipeline_config() -> dict[str, Any]:
    """Get configuration for waterfall processing pipeline.

    This should be used to set up the pipeline in Django admin with the following
    structure:

    Pipeline:
    - Name: ProcessingType.Waterfall.get_pipeline_name()
    - Schedule: None (manual launch)
    - Prevent overlapping runs: False (allow concurrent processing)

    Stages:
    1. "setup_stage" - setup_post_processing_cog (validates capture, creates records)
    2. "process_stage" - process_waterfall_data_cog (does download, processing, and
       storage)

    Tasks in each stage:
    - setup_stage: setup_post_processing_cog (capture_uuid and processing_types passed
      as runtime args)
    - process_stage: process_waterfall_data_cog (capture_uuid passed as runtime arg,
      depends on setup_stage)
    """
    from .models import ProcessingType

    return {
        "pipeline_name": ProcessingType.Waterfall.get_pipeline_name(),
        "prevent_overlapping_runs": False,
        "stages": [
            {
                "name": "setup_stage",
                "description": "Setup post-processing (validate capture, create "
                "records)",
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
        error_msg = f"Unknown pipeline type: {pipeline_type}"
        raise ValueError(error_msg)

    return config_func()


# Cog functions (pipeline steps)
@cog
def setup_post_processing_cog(
    capture_uuid: str, processing_types: list[str] | None = None
) -> None:
    """Setup post-processing for a capture.

    Args:
        capture_uuid: UUID of the capture to process
        processing_types: List of processing types to run
    Returns:
        None
    """
    try:
        logger.info(f"Starting setup for capture {capture_uuid}")

        # Import models here to avoid Django app registry issues
        from .models import Capture
        from .models import ProcessingType

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
                    raise ValueError(error_msg) from None

        # At this point, capture should not be None due to the retry logic above
        assert capture is not None, (
            f"Capture {capture_uuid} should have been found by now"
        )

        # Validate capture type
        # Import here to avoid Django app registry issues
        from .models import CaptureType

        if capture.capture_type != CaptureType.DigitalRF:
            error_msg = f"Capture {capture_uuid} is not a DigitalRF capture"
            raise ValueError(error_msg)  # noqa: TRY301

        # Set default processing types if not specified
        if not processing_types:
            processing_types = [ProcessingType.Waterfall.value]

        # Create PostProcessedData records for each processing type
        for processing_type in processing_types:
            _create_or_reset_processed_data(capture, processing_type)

        logger.info(f"Completed setup for capture {capture_uuid}")
    except Exception as e:
        logger.error(f"Setup failed for capture {capture_uuid}: {e}")
        raise


@cog
def process_waterfall_data_cog(
    capture_uuid: str, max_slices: int | None = None
) -> dict[str, Any]:
    """Process waterfall data for a capture.

    Args:
        capture_uuid: UUID of the capture to process
        max_slices: Maximum number of slices to process (default: None)

    Returns:
        Dict with status and processed data info
    """
    logger.info(f"Processing waterfall JSON data for capture {capture_uuid}")

    try:
        # Import models here to avoid Django app registry issues
        from .models import Capture
        from .models import PostProcessedData
        from .models import ProcessingType

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
                    max_slices=max_slices,
                )

                if waterfall_result["status"] != "success":
                    processed_data.mark_processing_failed(waterfall_result["message"])
                    raise ValueError(waterfall_result["message"])  # noqa: TRY301

                # Create a temporary JSON file
                import json

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


# Helper functions
def _create_or_reset_processed_data(capture, processing_type: str):
    """Create or reset a PostProcessedData record for a capture and processing type.

    Args:
        capture: The capture to create processed data for
        processing_type: Type of processing (waterfall, spectrogram, etc.)

    Returns:
        PostProcessedData: The created or reset record
    """
    # Import models here to avoid Django app registry issues
    from sds_gateway.api_methods.models import PostProcessedData
    from sds_gateway.api_methods.models import ProcessingStatus

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


def _process_waterfall_slice(params: WaterfallSliceParams) -> dict[str, Any] | None:
    """Process a single waterfall slice."""
    # Calculate sample range for this slice
    slice_start_sample = (
        params.start_sample + params.slice_idx * params.samples_per_slice
    )
    slice_num_samples = min(
        params.samples_per_slice, params.end_sample - slice_start_sample
    )

    if slice_num_samples <= 0:
        return None

    # Read the data
    data_array = params.reader.read_vector(
        slice_start_sample, slice_num_samples, params.channel, 0
    )

    # Perform FFT processing
    fft_data = np.fft.fft(data_array, n=params.fft_size)
    power_spectrum = np.abs(fft_data) ** 2

    # Convert to dB
    power_spectrum_db = 10 * np.log10(power_spectrum + 1e-12)

    # Convert power spectrum to binary string for transmission
    data_bytes = power_spectrum_db.astype(np.float32).tobytes()
    data_string = base64.b64encode(data_bytes).decode("utf-8")

    # Create timestamp from sample index
    timestamp = datetime.datetime.fromtimestamp(
        slice_start_sample / params.sample_rate, tz=datetime.UTC
    ).isoformat()

    # Build WaterfallFile format with enhanced metadata
    waterfall_file = {
        "data": data_string,
        "data_type": "float32",
        "timestamp": timestamp,
        "min_frequency": params.min_frequency,
        "max_frequency": params.max_frequency,
        "num_samples": slice_num_samples,
        "sample_rate": params.sample_rate,
        "center_frequency": params.center_freq,
    }

    # Build custom fields with all available metadata
    custom_fields = {
        "channel_name": params.channel,
        "start_sample": slice_start_sample,
        "num_samples": slice_num_samples,
        "fft_size": params.fft_size,
        "scan_time": slice_num_samples / params.sample_rate,
        "slice_index": params.slice_idx,
    }

    waterfall_file["custom_fields"] = custom_fields
    return waterfall_file


def reconstruct_drf_files(capture, capture_files, temp_path: Path) -> Path | None:
    """Reconstruct DigitalRF directory structure from SDS files."""
    # Import utilities here to avoid Django app registry issues
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


def convert_drf_to_waterfall_json(  # noqa: C901, PLR0915
    drf_path: Path,
    channel: str,
    processing_type: str,
    max_slices: int | None = None,
) -> dict[str, Any]:
    """Convert DigitalRF data to waterfall JSON format similar to SVI implementation."""
    logger.info(
        f"Converting DigitalRF data to waterfall JSON format for channel {channel}"
    )

    try:
        # Initialize DigitalRF reader
        reader = DigitalRFReader(str(drf_path))
        channels = reader.get_channels()

        if not channels:
            error_msg = "No channels found in DigitalRF data"
            raise ValueError(error_msg)  # noqa: TRY301

        if channel not in channels:
            error_msg = (
                f"Channel {channel} not found in DigitalRF data. "
                f"Available channels: {channels}"
            )
            raise ValueError(error_msg)  # noqa: TRY301

        # Get sample bounds
        bounds = reader.get_bounds(channel)
        if bounds is None:
            error_msg = "Could not get sample bounds for channel"
            raise ValueError(error_msg)  # noqa: TRY301

        start_sample, end_sample = bounds
        if start_sample is None or end_sample is None:
            error_msg = "Invalid sample bounds for channel"
            raise ValueError(error_msg)  # noqa: TRY301
        total_samples = end_sample - start_sample

        # Get metadata from DigitalRF properties
        drf_props_path = drf_path / channel / "drf_properties.h5"
        with h5py.File(drf_props_path, "r") as f:
            sample_rate_numerator = f.attrs.get("sample_rate_numerator")
            sample_rate_denominator = f.attrs.get("sample_rate_denominator")
            if sample_rate_numerator is None or sample_rate_denominator is None:
                error_msg = "Sample rate information missing from DigitalRF properties"
                raise ValueError(error_msg)  # noqa: TRY301
            sample_rate = float(sample_rate_numerator) / float(sample_rate_denominator)

        # Get center frequency from metadata
        center_freq = 0.0
        try:
            # Try to get center frequency from metadata
            metadata_dict = reader.read_metadata(
                start_sample, min(1000, end_sample - start_sample), channel
            )
            if metadata_dict and "center_freq" in metadata_dict:
                center_freq = float(metadata_dict["center_freq"])
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Could not read center frequency from metadata: {e}")

        # Calculate frequency range
        freq_span = sample_rate
        min_frequency = center_freq - freq_span / 2
        max_frequency = center_freq + freq_span / 2

        # Processing parameters
        fft_size = 1024  # Default, could be configurable
        samples_per_slice = 1024  # Default, could be configurable

        # Calculate total slices and limit to max_slices
        total_slices = total_samples // samples_per_slice
        slices_to_process = (
            min(total_slices, max_slices) if max_slices is not None else total_slices
        )

        logger.info(
            f"Processing {slices_to_process} slices with "
            f"{samples_per_slice} samples per slice"
        )

        # Process slices and create JSON data
        waterfall_data = []

        for slice_idx in range(slices_to_process):
            params = WaterfallSliceParams(
                reader=reader,
                channel=channel,
                slice_idx=slice_idx,
                start_sample=start_sample,
                samples_per_slice=samples_per_slice,
                end_sample=end_sample,
                fft_size=fft_size,
                min_frequency=min_frequency,
                max_frequency=max_frequency,
                sample_rate=sample_rate,
                center_freq=center_freq,
            )
            waterfall_file = _process_waterfall_slice(params)
            if waterfall_file:
                waterfall_data.append(waterfall_file)

            # Log progress
            if slice_idx % 400 == 0:
                logger.debug(f"Processed {slice_idx}/{slices_to_process} slices")

        metadata = {
            "center_frequency": center_freq,
            "sample_rate": sample_rate,
            "min_frequency": min_frequency,
            "max_frequency": max_frequency,
            "total_slices": total_slices,
            "slices_processed": len(waterfall_data),
            "fft_size": fft_size,
            "samples_per_slice": samples_per_slice,
            "channel": channel,
        }

        return {  # noqa: TRY300
            "status": "success",
            "message": "Waterfall data converted to JSON successfully",
            "json_data": waterfall_data,
            "metadata": metadata,
        }

    except Exception as e:
        logger.exception(f"Error converting DigitalRF to waterfall JSON: {e}")
        raise


def store_processed_data(
    capture_uuid: str,
    processing_type: str,
    curr_file_path: str,
    new_filename: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    from sds_gateway.api_methods.models import PostProcessedData

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
