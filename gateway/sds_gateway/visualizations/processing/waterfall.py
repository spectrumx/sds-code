"""Waterfall processing logic for visualizations."""

import base64
import datetime
import time
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger
from pydantic import Field
from pydantic import computed_field

from sds_gateway.visualizations.errors import SourceDataError

from .utils import DigitalRFParams
from .utils import validate_digitalrf_data

SAMPLES_PER_SLICE = 1024
FFT_SIZE = 1024


class WaterfallSliceParams(DigitalRFParams):
    """Parameters for processing a waterfall slice with validation."""

    slice_idx: int = Field(ge=0, description="Slice index")
    samples_per_slice: int = Field(gt=0, description="Number of samples per slice")

    @computed_field
    @property
    def slice_start_sample(self) -> int:
        """Calculate start sample for this slice."""
        return self.start_sample + self.slice_idx * self.samples_per_slice

    @computed_field
    @property
    def slice_num_samples(self) -> int:
        """Calculate number of samples for this slice."""
        return min(self.samples_per_slice, self.end_sample - self.slice_start_sample)

    @computed_field
    @property
    def timestamp(self) -> str:
        """Calculate timestamp for this slice."""
        return datetime.datetime.fromtimestamp(
            self.slice_start_sample / self.sample_rate, tz=datetime.UTC
        ).isoformat()


def validate_waterfall_data(
    drf_path: Path, channel: str, fft_size: int = FFT_SIZE
) -> WaterfallSliceParams:
    """
    Load DigitalRF data and return WaterfallSliceParams with validated attributes.

    This function loads DigitalRF data and creates a validated WaterfallSliceParams
    instance for waterfall processing.

    Args:
        drf_path: Path to DigitalRF data directory
        channel: Channel name to process

    Returns:
        WaterfallSliceParams: Validated parameters for waterfall processing

    Raises:
        ValidationError: If DigitalRF data is invalid or missing required information
    """
    # Get base DigitalRF parameters
    base_params = validate_digitalrf_data(drf_path, channel, fft_size)

    # Create WaterfallSliceParams with waterfall-specific defaults
    return WaterfallSliceParams(
        reader=base_params.reader,
        channel=base_params.channel,
        slice_idx=0,  # Will be updated per slice
        start_sample=base_params.start_sample,
        samples_per_slice=SAMPLES_PER_SLICE,
        end_sample=base_params.end_sample,
        fft_size=fft_size,
        center_freq=base_params.center_freq,
        sample_rate_numerator=base_params.sample_rate_numerator,
        sample_rate_denominator=base_params.sample_rate_denominator,
    )


def _process_waterfall_slice(params: WaterfallSliceParams) -> dict[str, Any] | None:
    """Process a single waterfall slice.

    Args:
        params: WaterfallSliceParams with slice index and other parameters

    Returns:
        Dictionary with slice data and metadata, or None if slice cannot be processed
        (e.g., due to data gaps or invalid sample range)
    """
    # Use computed properties for slice calculations
    if params.slice_num_samples <= 0:
        return None

    # Read the data with error handling for sample count mismatches
    # OSError covers file I/O errors and missing data blocks
    try:
        data_array = params.reader.read_vector(
            params.slice_start_sample, params.slice_num_samples, params.channel, 0
        )
    except OSError:
        # Data gap or missing file - return None to indicate slice unavailable
        return None

    # Perform FFT processing
    fft_data = np.fft.fft(data_array, n=params.fft_size)
    # Shift so DC is centered (required for correct frequency display)
    fft_data_shifted = np.fft.fftshift(fft_data)
    power_spectrum = np.abs(fft_data_shifted) ** 2

    # Convert to dB
    power_spectrum_db = 10 * np.log10(power_spectrum + 1e-12)

    # Convert power spectrum to binary string for transmission
    data_bytes = power_spectrum_db.astype(np.float32).tobytes()
    data_string = base64.b64encode(data_bytes).decode("utf-8")

    # Build WaterfallFile format with enhanced metadata
    return {
        "data": data_string,
        "data_type": "float32",
        "timestamp": params.timestamp,
        "min_frequency": params.min_frequency,
        "max_frequency": params.max_frequency,
        "num_samples": params.slice_num_samples,
        "sample_rate": params.sample_rate,
        "center_frequency": params.center_freq,
        "custom_fields": {
            "channel_name": params.channel,
            "start_sample": params.slice_start_sample,
            "num_samples": params.slice_num_samples,
            "fft_size": params.fft_size,
            "scan_time": params.slice_num_samples / params.sample_rate,
            "slice_index": params.slice_idx,
        },
    }


def compute_slices_on_demand(
    drf_path: Path,
    channel: str,
    start_index: int,
    end_index: int,
) -> dict[str, Any]:
    """Compute waterfall slices on-demand without full preprocessing.

    This function computes FFT slices for a specific range, enabling
    true streaming without pre-computing all slices upfront.

    Args:
        drf_path: Path to DigitalRF data directory
        channel: Channel name to process
        start_index: Starting slice index (inclusive)
        end_index: Ending slice index (exclusive)

    Returns:
        dict with 'slices', 'total_slices', 'start_index', 'end_index', 'metadata'
    """
    logger.info(
        f"Computing slices on-demand for channel {channel}: "
        f"range [{start_index}, {end_index})"
    )

    # Validate DigitalRF data and get base parameters
    base_params = validate_waterfall_data(drf_path, channel, FFT_SIZE)

    # Calculate total slices available
    total_slices = base_params.total_samples // SAMPLES_PER_SLICE

    # Validate and clamp indices
    start_index = max(start_index, 0)
    if start_index >= total_slices:
        return {
            "slices": [],
            "total_slices": total_slices,
            "start_index": start_index,
            "end_index": start_index,
            "metadata": _build_metadata(base_params, total_slices, 0),
        }

    end_index = min(end_index, total_slices)

    # Process only the requested slice range
    waterfall_slices = []
    failed_slices = 0
    for slice_idx in range(start_index, end_index):
        # Use shallow copy since we're only updating slice_idx (an integer)
        # The reader object is excluded from serialization, so no need for deep copy
        slice_params = base_params.model_copy(update={"slice_idx": slice_idx})
        waterfall_file = _process_waterfall_slice(slice_params)
        if waterfall_file:
            waterfall_slices.append(waterfall_file)
        else:
            failed_slices += 1

    if failed_slices > 0:
        logger.warning(
            f"Computed {len(waterfall_slices)} slices on-demand, "
            f"{failed_slices} slices failed (likely data gaps)"
        )
    else:
        logger.info(f"Computed {len(waterfall_slices)} slices on-demand")

    return {
        "slices": waterfall_slices,
        "total_slices": total_slices,
        "start_index": start_index,
        "end_index": end_index,
        "metadata": _build_metadata(base_params, total_slices, len(waterfall_slices)),
    }


def get_waterfall_power_bounds(
    drf_path: Path, channel: str, margin_fraction: float = 0.05
) -> dict[str, float] | None:
    """Compute power bounds from a small sample of slices for consistent color scale.

    Uses the same formula as the frontend calculatePowerBoundsFromSamples(): min/max
    over 3 slices (start, middle, end) plus a margin, so streaming and master match.

    Args:
        drf_path: Path to DigitalRF data directory
        channel: Channel name to process
        margin_fraction: Fraction of range to add as margin (default 0.05 = 5%)

    Returns:
        {"min": float, "max": float} or None if no valid data
    """
    base_params = validate_waterfall_data(drf_path, channel, FFT_SIZE)
    total_slices = base_params.total_samples // SAMPLES_PER_SLICE
    if total_slices == 0:
        return None

    # Same 3 slices as frontend: first, middle, last
    indices = [0, total_slices // 2, total_slices - 1]
    indices = [i for i in indices if i < total_slices]
    if not indices:
        return None

    global_min = float("inf")
    global_max = float("-inf")
    for slice_idx in indices:
        slice_params = base_params.model_copy(update={"slice_idx": slice_idx})
        slice_data = _process_waterfall_slice(slice_params)
        if slice_data is None:
            continue
        try:
            data_bytes = base64.b64decode(slice_data["data"])
            power_db = np.frombuffer(data_bytes, dtype=np.float32)
            finite = power_db[np.isfinite(power_db)]
            if finite.size > 0:
                global_min = min(global_min, float(np.min(finite)))
                global_max = max(global_max, float(np.max(finite)))
        except (ValueError, TypeError) as e:
            logger.debug("Skipping slice %s for power bounds: %s", slice_idx, e)
            continue

    if global_min == float("inf") or global_max == float("-inf"):
        return None
    span = global_max - global_min
    margin = span * margin_fraction
    return {"min": global_min - margin, "max": global_max + margin}


def get_waterfall_metadata(drf_path: Path, channel: str) -> dict[str, Any]:
    """Get waterfall metadata without processing any slices.

    This enables fast initial load by returning metadata immediately
    so the frontend knows total_slices and frequency bounds.

    Args:
        drf_path: Path to DigitalRF data directory
        channel: Channel name to process

    Returns:
        dict with metadata including total_slices, frequencies, sample_rate, etc.
    """
    logger.info(f"Getting waterfall metadata for channel {channel}")

    base_params = validate_waterfall_data(drf_path, channel, FFT_SIZE)
    total_slices = base_params.total_samples // SAMPLES_PER_SLICE

    return _build_metadata(base_params, total_slices, 0)


def _build_metadata(
    params: WaterfallSliceParams, total_slices: int, slices_processed: int
) -> dict[str, Any]:
    """Build metadata dict from waterfall parameters."""
    return {
        "center_frequency": params.center_freq,
        "sample_rate": params.sample_rate,
        "min_frequency": params.min_frequency,
        "max_frequency": params.max_frequency,
        "total_slices": total_slices,
        "slices_processed": slices_processed,
        "fft_size": params.fft_size,
        "samples_per_slice": SAMPLES_PER_SLICE,
        "channel": params.channel,
    }


def convert_drf_to_waterfall_json(
    drf_path: Path, channel: str, max_slices: int | None = None
) -> dict[str, Any]:
    """Convert DigitalRF data to waterfall JSON format similar to SVI implementation."""
    logger.info(
        f"Converting DigitalRF data to waterfall JSON format for channel {channel}"
    )

    # Validate DigitalRF data and get base parameters
    base_params = validate_waterfall_data(drf_path, channel, FFT_SIZE)

    # Calculate total slices and limit to max_slices
    total_slices = base_params.total_samples // SAMPLES_PER_SLICE
    slices_to_process = (
        min(total_slices, max_slices) if max_slices is not None else total_slices
    )

    logger.info(
        f"Processing {slices_to_process} slices with "
        f"{SAMPLES_PER_SLICE} samples per slice"
    )

    # Process slices and create JSON data
    waterfall_data = []
    skipped_slices = 0
    last_log_time = time.time()

    for slice_idx in range(slices_to_process):
        # Create slice-specific parameters by updating the base params
        # Use shallow copy since we're only updating slice_idx (an integer)
        slice_params = base_params.model_copy(update={"slice_idx": slice_idx})
        waterfall_file = _process_waterfall_slice(slice_params)
        if waterfall_file:
            waterfall_data.append(waterfall_file)
        else:
            skipped_slices += 1

        # Log progress every 3 seconds
        current_time = time.time()
        log_interval = 3.0
        if current_time - last_log_time >= log_interval:
            logger.debug(
                f"Processed {slice_idx + 1}/{slices_to_process} slices "
                f"(skipped: {skipped_slices})"
            )
            last_log_time = current_time

    if len(waterfall_data) == 0:
        msg = "No valid waterfall slices found"
        raise SourceDataError(msg)

    # Calculate power bounds from all slices for consistent color scaling
    global_min = float("inf")
    global_max = float("-inf")

    for slice_data in waterfall_data:
        # Decode the base64 data to calculate bounds
        data_bytes = base64.b64decode(slice_data["data"])
        power_spectrum_db = np.frombuffer(data_bytes, dtype=np.float32)

        slice_min = float(np.min(power_spectrum_db))
        slice_max = float(np.max(power_spectrum_db))

        global_min = min(global_min, slice_min)
        global_max = max(global_max, slice_max)

    power_scale_min = global_min if global_min != float("inf") else None
    power_scale_max = global_max if global_max != float("-inf") else None

    # Log final summary
    if power_scale_min is not None and power_scale_max is not None:
        logger.info(
            f"Waterfall processing complete: {len(waterfall_data)} slices processed, "
            f"{skipped_slices} slices skipped due to data issues. "
            f"Power bounds: [{power_scale_min:.2f}, {power_scale_max:.2f}] dB"
        )
    else:
        logger.warning(
            f"Waterfall processing complete: {len(waterfall_data)} slices processed, "
            f"{skipped_slices} slices skipped due to data issues. "
            "Power bounds could not be calculated."
        )

    metadata = {
        "center_frequency": base_params.center_freq,
        "sample_rate": base_params.sample_rate,
        "min_frequency": base_params.min_frequency,
        "max_frequency": base_params.max_frequency,
        "total_slices": total_slices,
        "slices_processed": len(waterfall_data),
        "slices_skipped": skipped_slices,
        "fft_size": base_params.fft_size,
        "samples_per_slice": SAMPLES_PER_SLICE,
        "channel": channel,
        "power_bounds": {
            "min": power_scale_min,
            "max": power_scale_max,
        },
    }

    return {
        "json_data": waterfall_data,
        "metadata": metadata,
    }
