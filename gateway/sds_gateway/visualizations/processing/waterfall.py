"""Waterfall processing logic for visualizations."""

import base64
import datetime
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import TypedDict

import h5py
import numpy as np
from digital_rf import DigitalRFReader
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
            assert file_path.is_relative_to(
                temp_path
            ), f"'{file_path=}' must be a subdirectory of '{temp_path=}'"
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


class WaterfallJsonResult(TypedDict):
    """Result of converting DigitalRF data to waterfall JSON format."""

    status: str
    message: str
    json_data: list[dict[str, Any]]
    metadata: dict[str, Any]


def _validate_drf_channel(reader: DigitalRFReader, channel: str) -> None:
    """Validate that the channel exists in the DigitalRF data."""
    channels = reader.get_channels()
    if not channels:
        error_msg = "No channels found in DigitalRF data"
        raise ValueError(error_msg)

    if channel not in channels:
        error_msg = (
            f"Channel {channel} not found in DigitalRF data. "
            f"Available channels: {channels}"
        )
        raise ValueError(error_msg)


def _get_sample_bounds(reader: DigitalRFReader, channel: str) -> tuple[int, int]:
    """Get and validate sample bounds for the channel."""
    bounds = reader.get_bounds(channel)
    if bounds is None:
        error_msg = "Could not get sample bounds for channel"
        raise ValueError(error_msg)

    start_sample, end_sample = bounds
    if start_sample is None or end_sample is None:
        error_msg = "Invalid sample bounds for channel"
        raise ValueError(error_msg)
    return start_sample, end_sample


def _get_sample_rate(drf_path: Path, channel: str) -> float:
    """Extract sample rate from DigitalRF properties."""
    drf_props_path = drf_path / channel / "drf_properties.h5"
    with h5py.File(drf_props_path, "r") as f:
        sample_rate_numerator = f.attrs.get("sample_rate_numerator")
        sample_rate_denominator = f.attrs.get("sample_rate_denominator")
        if sample_rate_numerator is None or sample_rate_denominator is None:
            error_msg = "Sample rate information missing from DigitalRF properties"
            raise ValueError(error_msg)
        return float(sample_rate_numerator) / float(sample_rate_denominator)


def _get_center_frequency(
    reader: DigitalRFReader, start_sample: int, end_sample: int, channel: str
) -> float:
    """Get center frequency from metadata, defaulting to 0.0 if not available."""
    center_freq = 0.0
    try:
        metadata_dict = reader.read_metadata(start_sample, end_sample, channel)
        if metadata_dict and "center_freq" in metadata_dict:
            center_freq = float(metadata_dict["center_freq"])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not read center frequency from metadata: {e}")
    return center_freq


def convert_drf_to_waterfall_lowres_json(
    drf_path: Path, channel: str
) -> WaterfallJsonResult:
    """Convert DigitalRF data to low-resolution waterfall JSON format for overview.

    This reuses the existing waterfall processing logic but with different parameters
    to create a compact overview suitable for navigation.
    """

    logger.info(
        f"Converting DigitalRF data to low-resolution waterfall JSON format "
        f"for channel {channel}"
    )

    try:
        # Reuse existing waterfall processing with overview-specific parameters
        overview_height = 200  # Fixed height for overview
        fft_size = 256  # Smaller FFT for overview
        samples_per_slice = 1024  # Same as regular waterfall

        # Get the regular waterfall result first with smaller FFT size
        regular_result = convert_drf_to_waterfall_json(
            drf_path, channel, fft_size=fft_size, samples_per_slice=samples_per_slice
        )

        if regular_result["status"] != "success":
            return regular_result

        regular_data = regular_result["json_data"]
        metadata = regular_result["metadata"]

        # Calculate how many slices to combine for overview
        total_slices = len(regular_data)
        slices_per_overview_row = max(1, total_slices // overview_height)

        logger.info(
            f"Creating overview from {total_slices} slices, combining "
            f"{slices_per_overview_row} slices per overview row"
        )

        # Group slices into overview rows
        overview_rows = []
        for i, slice_data in enumerate(regular_data):
            overview_row_idx = i // slices_per_overview_row

            if overview_row_idx >= len(overview_rows):
                overview_rows.append(
                    {"data": [], "timestamps": [], "slice_indices": []}
                )

            overview_rows[overview_row_idx]["data"].append(slice_data["data"])
            overview_rows[overview_row_idx]["timestamps"].append(
                slice_data["timestamp"]
            )
            overview_rows[overview_row_idx]["slice_indices"].append(i)

        # Create overview data by averaging slices in each row
        overview_data = []
        for row in overview_rows:
            if not row["data"]:
                continue

            # Parse and average the data for this row
            parsed_data = []
            for data_str in row["data"]:
                try:
                    binary_string = base64.b64decode(data_str)
                    bytes_array = np.frombuffer(binary_string, dtype=np.uint8)
                    float_array = np.frombuffer(bytes_array, dtype=np.float32)
                    parsed_data.append(float_array)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Failed to parse data for overview: {e}")
                    continue

            if parsed_data:
                # Average the power spectra for this row
                avg_data = np.mean(parsed_data, axis=0)

                # Convert back to base64
                data_bytes = avg_data.astype(np.float32).tobytes()
                data_string = base64.b64encode(data_bytes).decode("utf-8")

                # Use the first timestamp for this row
                timestamp = row["timestamps"][0] if row["timestamps"] else ""

                overview_slice = {
                    "data": data_string,
                    "data_type": "float32",
                    "timestamp": timestamp,
                    "min_frequency": metadata["min_frequency"],
                    "max_frequency": metadata["max_frequency"],
                    "num_samples": metadata["samples_per_slice"] * len(row["data"]),
                    "sample_rate": metadata["sample_rate"],
                    "center_frequency": metadata["center_frequency"],
                    "custom_fields": {
                        "channel_name": channel,
                        "overview_row": len(overview_data),
                        "slices_combined": len(row["data"]),
                        "slice_indices": row["slice_indices"],
                        "fft_size": fft_size,
                    },
                }
                overview_data.append(overview_slice)

        # Update metadata for overview
        overview_metadata = metadata.copy()
        overview_metadata.update(
            {
                "overview_rows": len(overview_data),
                "slices_per_overview_row": slices_per_overview_row,
                "fft_size": fft_size,
                "processing_type": "overview",
            }
        )

        return WaterfallJsonResult(
            status="success",
            message="Low-resolution waterfall data converted to JSON successfully",
            json_data=overview_data,
            metadata=overview_metadata,
        )

    except Exception as e:
        logger.exception(
            f"Error converting DigitalRF to low-resolution waterfall JSON: {e}"
        )
        raise


def convert_drf_to_waterfall_json(
    drf_path: Path,
    channel: str,
    max_slices: int | None = None,
    fft_size: int = 1024,
    samples_per_slice: int = 1024,
) -> WaterfallJsonResult:
    """Convert DigitalRF data to waterfall JSON format similar to SVI implementation.

    Args:
        drf_path: Path to DigitalRF data directory
        channel: Channel name to process
        max_slices: Maximum number of slices to process (None for all)
        fft_size: FFT size for processing (default: 1024)
        samples_per_slice: Number of samples per slice (default: 1024)
    """

    logger.info(
        f"Converting DigitalRF data to waterfall JSON format for channel {channel} "
        f"with FFT size {fft_size} and {samples_per_slice} samples per slice"
    )

    try:
        # Initialize DigitalRF reader and validate channel
        reader = DigitalRFReader(str(drf_path))
        _validate_drf_channel(reader, channel)

        # Get sample bounds
        start_sample, end_sample = _get_sample_bounds(reader, channel)
        total_samples = end_sample - start_sample

        # Get metadata
        sample_rate = _get_sample_rate(drf_path, channel)
        center_freq = _get_center_frequency(reader, start_sample, end_sample, channel)

        # Calculate frequency range
        freq_span = sample_rate
        min_frequency = center_freq - freq_span / 2
        max_frequency = center_freq + freq_span / 2

        # Calculate total slices and limit to max_slices
        total_slices = total_samples // samples_per_slice
        slices_to_process = (
            min(total_slices, max_slices) if max_slices is not None else total_slices
        )

        logger.info(
            f"Processing {slices_to_process} slices with "
            f"{samples_per_slice} samples per slice and FFT size {fft_size}"
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

        return WaterfallJsonResult(
            status="success",
            message="Waterfall data converted to JSON successfully",
            json_data=waterfall_data,
            metadata=metadata,
        )

    except Exception as e:
        logger.exception(f"Error converting DigitalRF to waterfall JSON: {e}")
        raise
