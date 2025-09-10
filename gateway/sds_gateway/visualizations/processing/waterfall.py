"""Waterfall processing logic for visualizations."""

import base64
import datetime
import os
import time
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from digital_rf import DigitalRFReader
from django.conf import settings
from loguru import logger
from pydantic import BaseModel
from pydantic import Field
from pydantic import computed_field
from pydantic import field_validator
from pydantic import model_validator

from sds_gateway.api_methods.utils.minio_client import get_minio_client


class WaterfallSliceParams(BaseModel):
    """Parameters for processing a waterfall slice with validation."""

    reader: Any = Field(exclude=True)  # Exclude from serialization
    channel: str = Field(min_length=1, description="Channel name")
    slice_idx: int = Field(ge=0, description="Slice index")
    start_sample: int = Field(ge=0, description="Start sample index")
    samples_per_slice: int = Field(gt=0, description="Number of samples per slice")
    end_sample: int = Field(gt=0, description="End sample index")
    fft_size: int = Field(gt=0, description="FFT size")
    center_freq: float = Field(description="Center frequency in Hz")
    sample_rate_numerator: int = Field(gt=0, description="Sample rate numerator")
    sample_rate_denominator: int = Field(gt=0, description="Sample rate denominator")

    @field_validator("end_sample")
    @classmethod
    def validate_end_sample(cls, v, info):
        """Validate that end_sample is greater than start_sample."""
        if "start_sample" in info.data and v <= info.data["start_sample"]:
            msg = "end_sample must be greater than start_sample"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def validate_channel_exists(self):
        """Validate that the channel exists in the DigitalRF data."""
        channels = self.reader.get_channels()
        if not channels:
            msg = "No channels found in DigitalRF data"
            raise ValueError(msg)
        if self.channel not in channels:
            msg = (
                f"Channel {self.channel} not found in DigitalRF data. "
                f"Available channels: {channels}"
            )
            raise ValueError(msg)
        return self

    @computed_field
    @property
    def sample_rate(self) -> float:
        """Calculate sample rate from numerator and denominator."""
        return float(self.sample_rate_numerator) / float(self.sample_rate_denominator)

    @computed_field
    @property
    def min_frequency(self) -> float:
        """Calculate minimum frequency."""
        return self.center_freq - self.sample_rate / 2

    @computed_field
    @property
    def max_frequency(self) -> float:
        """Calculate maximum frequency."""
        return self.center_freq + self.sample_rate / 2

    @computed_field
    @property
    def total_samples(self) -> int:
        """Calculate total number of samples."""
        return self.end_sample - self.start_sample

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

    class Config:
        arbitrary_types_allowed = True  # Allow DigitalRFReader type


def validate_digitalrf_data(drf_path: Path, channel: str) -> WaterfallSliceParams:
    """
    Load DigitalRF data and return WaterfallSliceParams with validated attributes.

    This function loads DigitalRF data and creates a validated WaterfallSliceParams
    instance. Pydantic handles all validation logic declaratively.

    Args:
        drf_path: Path to DigitalRF data directory
        channel: Channel name to process

    Returns:
        WaterfallSliceParams: Validated parameters for waterfall processing

    Raises:
        ValidationError: If DigitalRF data is invalid or missing required information
    """
    # Initialize DigitalRF reader
    reader = DigitalRFReader(str(drf_path))

    # Get sample bounds - let this fail naturally if invalid
    bounds = reader.get_bounds(channel)
    if bounds is None:
        msg = "Could not get sample bounds for channel"
        raise ValueError(msg)
    start_sample, end_sample = bounds
    if start_sample is None or end_sample is None:
        msg = "Invalid sample bounds for channel"
        raise ValueError(msg)

    # Get metadata from DigitalRF properties
    drf_props_path = drf_path / channel / "drf_properties.h5"
    with h5py.File(drf_props_path, "r") as f:
        sample_rate_numerator = f.attrs.get("sample_rate_numerator")
        sample_rate_denominator = f.attrs.get("sample_rate_denominator")
        if sample_rate_numerator is None or sample_rate_denominator is None:
            msg = "Sample rate information missing from DigitalRF properties"
            raise ValueError(msg)

    # Get center frequency from metadata (optional)
    center_freq = 0.0
    try:
        metadata_dict = reader.read_metadata(start_sample, end_sample, channel)
        if metadata_dict and "center_freq" in metadata_dict:
            center_freq = float(metadata_dict["center_freq"])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not read center frequency from metadata: {e}")

    # Create WaterfallSliceParams - Pydantic will validate everything
    return WaterfallSliceParams(
        reader=reader,
        channel=channel,
        slice_idx=0,  # Will be updated per slice
        start_sample=start_sample,
        samples_per_slice=1024,  # Default, will be updated per slice
        end_sample=end_sample,
        fft_size=1024,  # Default
        center_freq=center_freq,
        sample_rate_numerator=sample_rate_numerator,
        sample_rate_denominator=sample_rate_denominator,
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


def reconstruct_drf_files(capture, capture_files, temp_path: Path) -> Path | None:
    """Reconstruct DigitalRF directory structure from SDS files."""
    # Import utilities here to avoid Django app registry issues

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
        logger.warning("Could not find DigitalRF properties file")
        return None  # noqa: TRY300

    except Exception as e:  # noqa: BLE001
        logger.exception(f"Error reconstructing DigitalRF files: {e}")
        return None


def convert_drf_to_waterfall_json(
    drf_path: Path, channel: str, max_slices: int | None = None
) -> dict[str, Any]:
    """Convert DigitalRF data to waterfall JSON format similar to SVI implementation."""
    logger.info(
        f"Converting DigitalRF data to waterfall JSON format for channel {channel}"
    )

    # Validate DigitalRF data and get base parameters
    base_params = validate_digitalrf_data(drf_path, channel)

    # Processing parameters
    fft_size = 1024  # Default, could be configurable
    samples_per_slice = 1024  # Default, could be configurable

    # Calculate total slices and limit to max_slices
    total_slices = base_params.total_samples // samples_per_slice
    slices_to_process = (
        min(total_slices, max_slices) if max_slices is not None else total_slices
    )

    logger.info(
        f"Processing {slices_to_process} slices with "
        f"{samples_per_slice} samples per slice"
    )

    # Process slices and create JSON data
    waterfall_data = []
    last_log_time = time.time()

    for slice_idx in range(slices_to_process):
        # Create slice-specific parameters by updating the base params
        slice_params = base_params.model_copy(
            update={
                "slice_idx": slice_idx,
                "samples_per_slice": samples_per_slice,
                "fft_size": fft_size,
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
        "fft_size": fft_size,
        "samples_per_slice": samples_per_slice,
        "channel": channel,
    }

    return {
        "status": "success",
        "message": "Waterfall data converted to JSON successfully",
        "json_data": waterfall_data,
        "metadata": metadata,
    }
