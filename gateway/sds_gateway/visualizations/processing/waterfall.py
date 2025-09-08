"""Waterfall processing logic for visualizations."""

import base64
import datetime
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from digital_rf import DigitalRFReader
from django.conf import settings
from loguru import logger


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


def _process_waterfall_slice(params: WaterfallSliceParams) -> dict | None:
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
    from sds_gateway.api_methods.utils.minio_client import get_minio_client  # noqa: PLC0415

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
    drf_path: Path, channel: str, processing_type: str, max_slices: int | None = None
) -> dict:
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

            # Log progress every 10 slices
            if slice_idx % 10 == 0:
                logger.info(f"Processed {slice_idx}/{slices_to_process} slices")

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
