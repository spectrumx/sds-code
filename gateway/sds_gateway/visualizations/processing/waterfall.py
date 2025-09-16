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
    """Process a single waterfall slice."""
    # Use computed properties for slice calculations
    if params.slice_num_samples <= 0:
        return None

    # Read the data
    data_array = params.reader.read_vector(
        params.slice_start_sample, params.slice_num_samples, params.channel, 0
    )

    # Perform FFT processing
    fft_data = np.fft.fft(data_array, n=params.fft_size)
    power_spectrum = np.abs(fft_data) ** 2

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
    last_log_time = time.time()

    for slice_idx in range(slices_to_process):
        # Create slice-specific parameters by updating the base params
        slice_params = base_params.model_copy(
            update={
                "slice_idx": slice_idx,
                "samples_per_slice": SAMPLES_PER_SLICE,
                "fft_size": base_params.fft_size,
            }
        )
        waterfall_file = _process_waterfall_slice(slice_params)
        if waterfall_file:
            waterfall_data.append(waterfall_file)

        # Log progress every 2 seconds
        current_time = time.time()
        log_interval = 2.0
        if current_time - last_log_time >= log_interval:
            logger.debug(f"Processed {slice_idx}/{slices_to_process} slices")
            last_log_time = current_time

    metadata = {
        "center_frequency": base_params.center_freq,
        "sample_rate": base_params.sample_rate,
        "min_frequency": base_params.min_frequency,
        "max_frequency": base_params.max_frequency,
        "total_slices": total_slices,
        "slices_processed": len(waterfall_data),
        "fft_size": base_params.fft_size,
        "samples_per_slice": SAMPLES_PER_SLICE,
        "channel": channel,
    }

    return {
        "status": "success",
        "message": "Waterfall data converted to JSON successfully",
        "json_data": waterfall_data,
        "metadata": metadata,
    }
