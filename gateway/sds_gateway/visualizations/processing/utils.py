"""Shared utilities for visualization processing."""

import datetime
import os
from pathlib import Path
from typing import Any

import h5py
from digital_rf import DigitalRFReader
from django.conf import settings
from loguru import logger
from pydantic import BaseModel
from pydantic import Field
from pydantic import computed_field
from pydantic import field_validator
from pydantic import model_validator

from sds_gateway.api_methods.utils.minio_client import get_minio_client
from sds_gateway.visualizations.errors import ConfigurationError
from sds_gateway.visualizations.errors import SourceDataError


class DigitalRFParams(BaseModel):
    """Base parameters for processing DigitalRF data with validation."""

    reader: Any = Field(exclude=True)  # Exclude from serialization
    channel: str = Field(min_length=1, description="Channel name")
    start_sample: int = Field(ge=0, description="Start sample index")
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
            raise SourceDataError(msg)
        if self.channel not in channels:
            msg = (
                f"Channel {self.channel} not found in DigitalRF data. "
                f"Available channels: {channels}"
            )
            raise ConfigurationError(msg)
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

    class Config:
        arbitrary_types_allowed = True  # Allow DigitalRFReader type


def validate_digitalrf_data(
    drf_path: Path, channel: str, fft_size: int = 1024
) -> DigitalRFParams:
    """
    Load DigitalRF data and return DigitalRFParams with validated attributes.

    This function loads DigitalRF data and creates a validated DigitalRFParams
    instance. Pydantic handles all validation logic declaratively.

    Args:
        drf_path: Path to DigitalRF data directory
        channel: Channel name to process

    Returns:
        DigitalRFParams: Validated parameters for DigitalRF processing

    Raises:
        ValidationError: If DigitalRF data is invalid or missing required information
    """
    # Initialize DigitalRF reader
    try:
        reader = DigitalRFReader(str(drf_path))
    except Exception as e:
        msg = f"Could not initialize DigitalRF reader: {e}"
        raise SourceDataError(msg) from e

    # Get sample bounds - let this fail naturally if invalid
    try:
        bounds = reader.get_bounds(channel)
    except Exception as e:
        msg = "Could not get sample bounds for channel"
        raise SourceDataError(msg) from e

    if bounds is None or bounds[0] is None or bounds[1] is None:
        msg = "Could not get sample bounds for channel"
        raise SourceDataError(msg)
    start_sample, end_sample = bounds[0], bounds[1]

    # Get metadata from DigitalRF properties
    drf_props_path = drf_path / channel / "drf_properties.h5"
    with h5py.File(drf_props_path, "r") as f:
        sample_rate_numerator = f.attrs.get("sample_rate_numerator")
        sample_rate_denominator = f.attrs.get("sample_rate_denominator")
        if sample_rate_numerator is None or sample_rate_denominator is None:
            msg = "Sample rate information missing from DigitalRF properties"
            raise SourceDataError(msg)

    # Get center frequency from metadata (optional)
    center_freq = 0.0
    try:
        metadata_dict = reader.read_metadata(start_sample, end_sample, channel)
        if metadata_dict and "center_freq" in metadata_dict:
            center_freq = float(metadata_dict["center_freq"])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not read center frequency from metadata: {e}")

    # Create DigitalRFParams
    return DigitalRFParams(
        reader=reader,
        channel=channel,
        start_sample=start_sample,
        end_sample=end_sample,
        fft_size=fft_size,
        center_freq=center_freq,
        sample_rate_numerator=sample_rate_numerator,
        sample_rate_denominator=sample_rate_denominator,
    )


def _get_drf_cache_dir() -> Path:
    """Get the directory for caching reconstructed DRF files."""
    cache_dir = Path(settings.MEDIA_ROOT) / "drf_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _find_drf_root(directory: Path) -> Path | None:
    """Find DigitalRF root directory by locating drf_properties.h5.

    Args:
        directory: Directory to search in

    Returns:
        Path to DRF root directory (parent of channel directory) if found,
        None otherwise.
    """
    if not directory.exists():
        return None

    # Check if drf_properties.h5 exists (indicates valid DRF structure)
    for root, _dirs, files in os.walk(directory):
        if "drf_properties.h5" in files:
            # The DigitalRF root is the parent of the channel directory
            return Path(root).parent

    return None


def get_cached_drf_path(capture_uuid: str) -> Path | None:
    """Check if reconstructed DRF files are already cached.

    Returns:
        Path to cached DRF root directory if it exists and is valid, None otherwise.
    """
    cache_dir = _get_drf_cache_dir()
    capture_cache = cache_dir / str(capture_uuid)

    drf_root = _find_drf_root(capture_cache)
    if drf_root:
        logger.info(f"Using cached DRF files at: {drf_root}")
    return drf_root


def reconstruct_drf_files(capture, capture_files, temp_path: Path) -> Path:
    """Reconstruct DigitalRF directory structure from SDS files.

    This function now supports persistent caching - if files are already cached,
    it returns the cached path immediately.

    Note:
        The ``temp_path`` parameter is **intentionally ignored**. It is retained
        solely for backward API compatibility with older callers that still pass
        a temporary directory path. Callers may pass any ``Path`` value; it will
        not affect the behavior of this function. This parameter is considered
        deprecated and may be removed in a future major release.
    Args:
        capture: Capture model instance
        capture_files: QuerySet of File objects for this capture
        temp_path: Deprecated; ignored temporary directory path kept for API
            compatibility. Its value is not used.
    Returns:
        Path: Path to the DigitalRF root directory

    Raises:
        SourceDataError: If reconstruction fails due to data issues
    """
    # Check cache first
    cached_path = get_cached_drf_path(capture.uuid)
    if cached_path:
        return cached_path

    logger.info("Reconstructing DigitalRF directory structure (not cached)")

    # First, check if we have the required drf_properties.h5 file
    has_properties_file = any(
        file_obj.name == "drf_properties.h5" for file_obj in capture_files
    )
    if not has_properties_file:
        error_msg = (
            "drf_properties.h5 file not found in capture files. "
            "This file is required for DigitalRF processing."
        )
        logger.error(error_msg)
        raise SourceDataError(error_msg)

    minio_client = get_minio_client()

    # Use persistent cache directory instead of temp directory
    cache_dir = _get_drf_cache_dir()
    capture_dir = cache_dir / str(capture.uuid)
    capture_dir.mkdir(parents=True, exist_ok=True)

    # Download and place files in the correct structure
    # Use count() to avoid materializing entire queryset
    total_files = capture_files.count()
    for idx, file_obj in enumerate(capture_files):
        # Create the directory structure using Path operations for safety
        file_path = (capture_dir / file_obj.directory / file_obj.name).resolve()
        if not file_path.is_relative_to(cache_dir):
            error_msg = (
                f"Invalid file path during reconstruction: "
                f"'{file_path=}' must be a subdirectory of '{cache_dir=}'"
            )
            logger.error(error_msg)
            raise SourceDataError(error_msg)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Skip if file already exists (partial cache recovery)
        if file_path.exists():
            continue

        # Download the file from MinIO
        logger.debug(f"Downloading file {idx + 1}/{total_files}: {file_obj.name}")
        minio_client.fget_object(
            bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
            object_name=file_obj.file.name,
            file_path=str(file_path),
        )

    # Find the DigitalRF root directory using shared helper
    drf_root = _find_drf_root(capture_dir)
    if drf_root is None:
        # This should never happen since we checked for the file above
        error_msg = "DigitalRF root directory not found after reconstruction"
        logger.error(error_msg)
        raise SourceDataError(error_msg)

    logger.info(f"Found DigitalRF root at: {drf_root}")
    return drf_root


def store_processed_data(
    capture_uuid: str,
    processing_type: str,
    curr_file_path: str,
    new_filename: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Store processed data back to SDS storage as a file.

    Args:
        capture_uuid: UUID of the capture
        processing_type: Type of processed data (waterfall, spectrogram, etc.)
        file_path: Path to the file to store
        filename: New name for the stored file
        metadata: Metadata to store

    Returns:
        None
    """
    from sds_gateway.api_methods.models import Capture  # noqa: PLC0415
    from sds_gateway.visualizations.models import PostProcessedData  # noqa: PLC0415

    logger.info(f"Storing {processing_type} file for capture {capture_uuid}")

    capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)

    # Get the processed data record
    processed_data = PostProcessedData.objects.filter(
        capture=capture,
        processing_type=processing_type,
    ).first()

    if not processed_data:
        error_msg = f"No processed data record found for {processing_type}"
        raise ValueError(error_msg)

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
