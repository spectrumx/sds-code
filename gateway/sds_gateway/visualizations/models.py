"""Models for the visualizations app."""

import datetime
import re
import uuid
from enum import StrEnum
from pathlib import Path

from django.db import models
from django_cog.models import Pipeline


class ProcessingType(StrEnum):
    """The type of post-processing."""

    Waterfall = "waterfall"
    Spectrogram = "spectrogram"

    def get_pipeline_name(self) -> str:
        """Get the pipeline name for this processing type."""
        return f"{self.value}_processing"


class ProcessingStatus(StrEnum):
    """The status of post-processing."""

    Pending = "pending"
    Processing = "processing"
    Completed = "completed"
    Failed = "failed"


class BaseModel(models.Model):
    """
    Superclass for all models in the visualizations app.
    """

    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(blank=True, null=True)
    is_deleted = models.BooleanField(default=False)
    is_public = models.BooleanField(default=False)

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Allows this class to be abstract."""

        abstract = True

    def soft_delete(self) -> None:
        """Soft delete this record by marking it as deleted."""
        self.is_deleted = True
        self.deleted_at = datetime.datetime.now(datetime.UTC)
        self.save()


class PostProcessedData(BaseModel):
    """
    Generalized model to store post-processed data for captures.

    This model can store any type of post-processed data (waterfall, spectrogram, etc.)
    and tracks processing status and metadata.
    """

    capture = models.ForeignKey(
        "api_methods.Capture",
        on_delete=models.CASCADE,
        related_name="visualization_post_processed_data",
        help_text="The capture this processed data belongs to",
    )

    processing_type = models.CharField(
        max_length=50,
        choices=[(pt.value, pt.value.title()) for pt in ProcessingType],
        help_text="Type of post-processing (waterfall, spectrogram, etc.)",
    )

    # Processing parameters (stored as JSON for flexibility)
    processing_parameters = models.JSONField(
        default=dict,
        help_text="Processing parameters (FFT size, window type, etc.)",
    )

    # Data storage - file-based
    data_file = models.FileField(
        upload_to="post_processed_data/",
        help_text="File containing the processed data",
        blank=True,
        null=True,
    )

    # Metadata (stored as JSON for flexibility)
    metadata = models.JSONField(
        default=dict,
        help_text="Processing metadata (frequencies, timestamps, etc.)",
    )

    # Processing status
    processing_status = models.CharField(
        max_length=20,
        choices=[(ps.value, ps.title()) for ps in ProcessingStatus],
        default=ProcessingStatus.Pending.value,
        help_text="Current processing status",
    )
    processing_error = models.TextField(
        blank=True,
        help_text="Error message if processing failed",
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the processing was completed",
    )

    # Cog pipeline tracking
    pipeline_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="Cog pipeline ID for tracking",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Post processed data"
        indexes = [
            models.Index(fields=["capture", "processing_type"]),
            models.Index(fields=["processing_status"]),
            models.Index(fields=["pipeline_id"]),
        ]

    def __str__(self):
        return (
            f"{self.processing_type} data for {self.capture.name} "
            f"({self.processing_status})"
        )

    def mark_processing_started(self, pipeline_id: str | None = None) -> None:
        """Mark processing as started."""
        self.processing_status = ProcessingStatus.Processing.value
        if pipeline_id:
            self.pipeline_id = pipeline_id
        self.save(update_fields=["processing_status", "pipeline_id"])

    def mark_processing_completed(self) -> None:
        """Mark processing as completed."""
        self.processing_status = ProcessingStatus.Completed.value
        self.processed_at = datetime.datetime.now(datetime.UTC)
        self.save(update_fields=["processing_status", "processed_at"])

    def mark_processing_failed(self, error_message: str) -> None:
        """Mark processing as failed with error message."""
        self.processing_status = ProcessingStatus.Failed.value
        self.processing_error = error_message
        self.save(update_fields=["processing_status", "processing_error"])

    def set_processed_data_file(self, file_path: str, filename: str) -> None:
        """Set the processed data file."""
        with Path(file_path).open("rb") as f:
            self.data_file.save(filename, f, save=False)
        self.save(update_fields=["data_file"])


def get_latest_pipeline_by_base_name(base_name: str):
    """
    Get the latest pipeline by base name, handling timestamped pipelines from smart
    recreation.

    Args:
        base_name: The base name of the pipeline (e.g.,
        ProcessingType.Waterfall.get_pipeline_name())

    Returns:
        Pipeline: The most recent pipeline with this base name, or None if not found

    Example:
        - If "waterfall_processing_20241220_143052" exists: returns that pipeline
        - If multiple versioned pipelines exist: returns the most recent one
    """

    # Look for timestamped pipelines with this base name (primary method)
    # Use string pattern for Django regex filter, not compiled pattern
    pattern_string = f"^{re.escape(base_name)}_\\d{{8}}_\\d{{6}}$"

    versioned_pipelines = Pipeline.objects.filter(
        name__regex=pattern_string, enabled=True
    ).order_by("-created_date")

    if versioned_pipelines.exists():
        return versioned_pipelines.first()

    # Fallback: try exact match (for backward compatibility)
    try:
        return Pipeline.objects.get(name=base_name, enabled=True)
    except Pipeline.DoesNotExist:
        pass

    # Final fallback: try partial match
    partial_matches = Pipeline.objects.filter(
        name__startswith=base_name, enabled=True
    ).order_by("-created_date")

    if partial_matches.exists():
        return partial_matches.first()

    return None
