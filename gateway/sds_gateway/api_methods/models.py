"""Describes the models for the API methods."""

import datetime
import json
import logging
import uuid
from enum import StrEnum
from pathlib import Path
from typing import Any
from typing import cast

from blake3 import blake3 as Blake3  # noqa: N812
from django.conf import settings
from django.db import models
from django.db.models import ProtectedError
from django.db.models import QuerySet
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .utils.metadata_schemas import infer_index_name
from .utils.opensearch_client import get_opensearch_client

log = logging.getLogger(__name__)


class CaptureType(StrEnum):
    """The type of radiofrequency capture."""

    DigitalRF = "drf"
    RadioHound = "rh"
    SigMF = "sigmf"


class CaptureOrigin(StrEnum):
    """How a capture was created."""

    System = "system"
    User = "user"


class KeySources(StrEnum):
    """The source of an SDS API key."""

    SDSWebUI = "sds_web_ui"
    SVIBackend = "svi_backend"
    SVIWebUI = "svi_web_ui"


class ItemType(StrEnum):
    """The type of item that can be shared."""

    DATASET = "dataset"
    CAPTURE = "capture"


def default_expiration_date() -> datetime.datetime:
    """Returns the default expiration date for a file."""
    # 2 years from now
    return datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=730)


class BaseModel(models.Model):
    """
    Superclass for all models in the API methods app.
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


class ProtectedFileQuerySet(QuerySet["File"]):
    """Custom QuerySet to protect against deletion of files."""

    def delete(self) -> tuple[int, dict[str, int]]:
        """Override the delete method to raise ProtectedError if needed."""
        for obj in self:
            raise_if_file_deletion_is_blocked(instance=obj)
        return super().delete()


class File(BaseModel):
    """
    Model to define files uploaded through the API.
    """

    directory = models.CharField(max_length=2048, default="files/")
    expiration_date = models.DateTimeField(default=default_expiration_date)
    file = models.FileField(upload_to="files/")
    media_type = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255, blank=True)
    permissions = models.CharField(max_length=9, default="rw-r--r--")
    size = models.IntegerField(blank=True)
    sum_blake3 = models.CharField(max_length=64, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        related_name="files",
        on_delete=models.PROTECT,  # prevents users from being deleted if they own files (delete the files first). # noqa: E501
    )
    bucket_name = models.CharField(
        max_length=255,
        default=settings.AWS_STORAGE_BUCKET_NAME,
    )
    dataset = models.ForeignKey(
        "Dataset",
        blank=True,
        null=True,
        related_name="files",
        on_delete=models.SET_NULL,
    )
    capture = models.ForeignKey(
        "Capture",
        blank=True,
        null=True,
        related_name="files",
        on_delete=models.SET_NULL,
    )

    # manager override
    objects = ProtectedFileQuerySet.as_manager()

    def __str__(self) -> str:
        return f"{self.directory}{self.name}"

    @property
    def user_directory(self) -> str:
        """Returns the path relative to the user root on SDS."""
        # TODO: make this the default ".directory" behavior after the workshop
        return str(Path(*self.directory.parts[2:]))

    def calculate_checksum(self, file_obj=None) -> str:
        """Calculates the BLAKE3 checksum of the file."""
        checksum = Blake3()  # pylint: disable=not-callable
        file = self.file
        if file_obj:
            file = file_obj

        for chunk in file.chunks():
            checksum.update(chunk)
        return checksum.hexdigest()

    def delete(self, *args, **kwargs) -> tuple[int, dict[str, int]]:
        """Hard delete this record after checking for blockers."""
        raise_if_file_deletion_is_blocked(instance=self)
        return super().delete(*args, **kwargs)

    def soft_delete(self) -> None:
        """Soft delete this record after checking for blockers."""
        raise_if_file_deletion_is_blocked(instance=self)
        return super().soft_delete()


def raise_if_file_deletion_is_blocked(instance: File) -> None:
    """Raises an error if the file passed can't be deleted.

    Raises:
        ProtectedError if the file is associated with a capture or dataset.
    """
    associations: list[str] = []
    if instance.capture and not instance.capture.is_deleted:
        associations.append(f"capture ({instance.capture.uuid})")
    if instance.dataset and not instance.dataset.is_deleted:
        associations.append(f"dataset ({instance.dataset.uuid})")
    if not associations:
        return
    msg = (
        f"Cannot delete file '{instance.name}': it is "
        f"associated with {' and '.join(associations)}."
        " Delete the associated object(s) first."
    )
    raise ProtectedError(msg, protected_objects={instance})


@receiver(pre_delete, sender=File)
def prevent_file_deletion(sender, instance: File, **kwargs) -> None:
    """Prevents deletion of files associated with captures or datasets.

    Version to cover bulk deletions from querysets.
    """
    raise_if_file_deletion_is_blocked(instance=instance)


class Capture(BaseModel):
    """
    Model to define captures (specific file type) uploaded through the API.
    """

    CAPTURE_TYPE_CHOICES = [
        (CaptureType.DigitalRF, "Digital RF"),
        (CaptureType.RadioHound, "RadioHound"),
        (CaptureType.SigMF, "SigMF"),
    ]
    ORIGIN_CHOICES = [
        (CaptureOrigin.System, "System"),
        (CaptureOrigin.User, "User"),
    ]

    channel = models.CharField(max_length=255, blank=True)  # DRF
    scan_group = models.UUIDField(blank=True, null=True)  # RH
    capture_type = models.CharField(
        max_length=255,
        choices=CAPTURE_TYPE_CHOICES,
        default=CaptureType.DigitalRF,
    )
    top_level_dir = models.CharField(max_length=2048, blank=True)
    index_name = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        related_name="captures",
        on_delete=models.PROTECT,
    )
    origin = models.CharField(
        max_length=255,
        choices=ORIGIN_CHOICES,
        default=CaptureOrigin.User,
    )
    dataset = models.ForeignKey(
        "Dataset",
        blank=True,
        null=True,
        related_name="captures",
        on_delete=models.SET_NULL,
    )
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="shared_captures",
    )

    def __str__(self):
        if self.name:
            return f"{self.name} ({self.capture_type})"
        return f"{self.capture_type} capture for channel {self.channel} added on {self.created_at}"  # noqa: E501

    def save(self, *args, **kwargs):
        """Save the capture, setting default name from top_level_dir if not provided."""
        if not self.name and self.top_level_dir:
            # Extract the last part of the path as the default name
            self.name = Path(self.top_level_dir).name or self.top_level_dir.strip("/")

        # Set the index_name if not provided
        if not self.index_name and self.capture_type:
            # Convert string to CaptureType enum
            capture_type_enum = CaptureType(self.capture_type)
            self.index_name = infer_index_name(capture_type_enum)

        super().save(*args, **kwargs)

    @property
    def center_frequency_ghz(self) -> float | None:
        """Get center frequency in GHz from OpenSearch."""
        frequency_data = self.get_opensearch_frequency_metadata()
        center_freq_hz = frequency_data.get("center_frequency")
        if center_freq_hz:
            return center_freq_hz / 1e9
        return None

    @property
    def sample_rate_mhz(self) -> float | None:
        """Get sample rate in MHz from OpenSearch."""
        frequency_data = self.get_opensearch_frequency_metadata()
        sample_rate_hz = frequency_data.get("sample_rate")
        if sample_rate_hz:
            return sample_rate_hz / 1e6
        return None

    @property
    def is_multi_channel(self) -> bool:
        """Check if this capture is a multi-channel capture."""
        match self.capture_type:
            case CaptureType.DigitalRF:
                captures_in_top_level_dir = Capture.objects.filter(
                    top_level_dir=self.top_level_dir,
                    capture_type=self.capture_type,
                    owner=self.owner,
                    is_deleted=False,
                ).count()
                return captures_in_top_level_dir > 1
            case _:
                return False

    def get_capture_type_display(self) -> str:
        """Get the display value for the capture type."""
        return dict(self.CAPTURE_TYPE_CHOICES).get(self.capture_type, self.capture_type)

    def get_capture(self) -> dict[str, Any]:
        """Return a Capture or composite of Captures for multi-channel captures.

        Returns:
            dict: Either a single capture or composite capture data
        """
        # If this is not a multi-channel capture, return the capture itself
        if not self.is_multi_channel:
            return {"capture": self, "is_composite": False}

        # For multi-channel captures, find all captures with the same top_level_dir
        related_captures = Capture.objects.filter(
            top_level_dir=self.top_level_dir,
            capture_type=self.capture_type,
            owner=self.owner,
            is_deleted=False,
        ).order_by("channel")

        if related_captures.count() <= 1:
            # Only one capture found, return as single capture
            return {"capture": self, "is_composite": False}

        # Multiple captures found, create composite
        return {
            "captures": list(related_captures),
            "is_composite": True,
            "top_level_dir": self.top_level_dir,
            "capture_type": self.capture_type,
            "owner": self.owner,
        }

    def get_opensearch_frequency_metadata(self) -> dict[str, Any]:
        """
        Query OpenSearch for frequency metadata for this specific capture.

        Returns:
            dict: Frequency metadata (center_frequency, sample_rate, etc.)
        """

        try:
            client = get_opensearch_client()

            query = {
                "query": {"term": {"_id": str(self.uuid)}},
                "_source": ["search_props", "capture_props"],
            }

            # Get the index name for this capture type
            # Handle both enum objects and string values from database
            if hasattr(self.capture_type, "value"):
                # It's an enum object
                index_name = f"captures-{self.capture_type.value}"
            else:
                # It's already a string value
                index_name = f"captures-{self.capture_type}"

            log.info(
                "Querying OpenSearch index '%s' for capture %s", index_name, self.uuid
            )

            response = client.search(
                index=index_name,
                body=query,
                size=1,  # pyright: ignore[reportCallIssue]
            )

            if response["hits"]["total"]["value"] > 0:
                source = response["hits"]["hits"][0]["_source"]
                return self._extract_frequency_metadata_from_source(source)

            log.warning("No OpenSearch data found for capture %s", self.uuid)

        except Exception:
            log.exception("Error querying OpenSearch for capture %s", self.uuid)

        return {}

    def _extract_frequency_metadata_from_source(
        self, source: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract frequency metadata from OpenSearch source data."""

        search_props = source.get("search_props", {})
        log.info("OpenSearch data for %s: search_props=%s", self.uuid, search_props)

        # Try search_props first (preferred)
        center_frequency = search_props.get("center_frequency")
        sample_rate = search_props.get("sample_rate")

        # If search_props missing, try to read from capture_props directly
        if not center_frequency or not sample_rate:
            capture_props = source.get("capture_props", {})
            log.info(
                "search_props incomplete, checking capture_props: %s",
                list(capture_props.keys()),
            )

            if self.capture_type == CaptureType.DigitalRF:
                center_frequency, sample_rate = _extract_drf_capture_props(
                    capture_props=capture_props,
                    center_frequency=center_frequency,
                    sample_rate=sample_rate,
                    capture_uuid=str(self.uuid),
                )
            elif self.capture_type == CaptureType.RadioHound:
                center_frequency, sample_rate = _extract_radiohound_capture_props(
                    capture_props=capture_props,
                    center_frequency=center_frequency,
                    sample_rate=sample_rate,
                )

        return {
            "center_frequency": center_frequency,
            "sample_rate": sample_rate,
            "frequency_min": search_props.get("frequency_min"),
            "frequency_max": search_props.get("frequency_max"),
        }

    @classmethod
    def bulk_load_frequency_metadata(
        cls, captures: QuerySet["Capture"]
    ) -> dict[str, dict[str, Any]]:
        """
        Efficiently load frequency metadata for multiple captures in
        one OpenSearch query.

        Args:
            captures: QuerySet or list of Capture objects
        Returns:
            dict: {capture_uuid: frequency_metadata_dict}
        """
        try:
            client = get_opensearch_client()

            # Group captures by type for separate queries
            captures_by_type = _group_captures_by_type(captures)
            frequency_data = {}

            # Query each capture type separately
            for capture_type, type_captures in captures_by_type.items():
                type_frequency_data = _query_capture_type_metadata(
                    client=client,
                    capture_type=capture_type,
                    type_captures=type_captures,
                )
                frequency_data.update(type_frequency_data)

        except Exception:
            log.exception("Error bulk loading frequency metadata")
            return {}
        else:
            return frequency_data

    def debug_opensearch_response(self) -> dict[str, Any] | None:
        """
        Debug method to see exactly what OpenSearch returns for this capture.
        This will help us understand why frequency metadata extraction is failing.
        """

        try:
            client = get_opensearch_client()

            # Handle both enum objects and string values from database
            if hasattr(self.capture_type, "value"):
                # It's an enum object
                index_name = f"captures-{self.capture_type.value}"
            else:
                # It's already a string value
                index_name = f"captures-{self.capture_type}"

            query = {"query": {"term": {"_id": str(self.uuid)}}}

            log.debug("=== DEBUG: OpenSearch Query ===")
            log.debug("Index: %s", index_name)
            log.debug("UUID: %s", self.uuid)
            log.debug("Query: %s", query)

            response = client.search(
                index=index_name,
                body=query,
                size=1,  # pyright: ignore[reportCallIssue]
            )

            log.debug("=== DEBUG: OpenSearch Response ===")
            log.debug("Total hits: %s", response["hits"]["total"]["value"])

            if response["hits"]["total"]["value"] > 0:
                source = response["hits"]["hits"][0]["_source"]
                log.debug("=== DEBUG: Full Source Data ===")
                log.debug("Source keys: %s", list(source.keys()))

                search_props = source.get("search_props", {})
                log.debug("=== DEBUG: search_props ===")
                log.debug("search_props keys: %s", list(search_props.keys()))
                log.debug("search_props content: %s", search_props)

                capture_props = source.get("capture_props", {})
                log.debug("=== DEBUG: capture_props ===")
                log.debug("capture_props keys: %s", list(capture_props.keys()))
                if capture_props:
                    # Just show a few key fields to avoid log spam
                    key_fields = [
                        "center_freq",
                        "center_frequency",
                        "sample_rate",
                        "sample_rate_numerator",
                        "sample_rate_denominator",
                        "samples_per_second",
                    ]
                    for field in key_fields:
                        if field in capture_props:
                            log.debug(
                                "capture_props.%s = %s", field, capture_props[field]
                            )

                return source
        except Exception:
            log.exception("=== DEBUG: Exception occurred ===")
            log.exception("Error occurred during frequency metadata extraction")
            return None
        else:
            log.debug("=== DEBUG: No data found ===")
            return None


class Dataset(BaseModel):
    """
    Model for datasets defined and created through the API.

    Schema Definition: https://github.com/spectrumx/schema-definitions/blob/master/definitions/sds/abstractions/dataset/README.md
    """

    list_fields = ["authors", "keywords", "institutions"]

    name = models.CharField(max_length=255, blank=False, default=None)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        related_name="datasets",
        on_delete=models.PROTECT,
    )
    abstract = models.TextField(blank=True)
    description = models.TextField(blank=True)
    doi = models.CharField(max_length=255, blank=True)
    authors = models.TextField(blank=True)
    license = models.CharField(max_length=255, blank=True)
    keywords = models.TextField(blank=True)
    institutions = models.TextField(blank=True)
    release_date = models.DateTimeField(blank=True, null=True)
    repository = models.URLField(blank=True)
    version = models.CharField(max_length=255, blank=True)
    website = models.URLField(blank=True)
    provenance = models.JSONField(blank=True, null=True)
    citation = models.JSONField(blank=True, null=True)
    other = models.JSONField(blank=True, null=True)
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="shared_datasets",
    )

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs) -> None:
        # Serialize the list fields to a JSON string before saving
        for field in self.list_fields:
            field_value = getattr(self, field)
            if field_value:
                if isinstance(field_value, list):
                    setattr(self, field, json.dumps(field_value))
                elif isinstance(field_value, str):
                    # If it's already a string, it might be JSON - try to parse it
                    try:
                        # Validate that it's valid JSON
                        json.loads(field_value)
                        # If it's already valid JSON, leave it as is
                    except (json.JSONDecodeError, TypeError):
                        # If it's not valid JSON, raise an error
                        msg = (
                            f"A field you are trying to populate ('{field}') "
                            "must be a list, but you provided a value of type: "
                            f"{type(field_value).__name__}. For your convenience, "
                            f"the list fields in this table include: "
                            f"{self.list_fields!s}."
                        )
                        raise ValueError(msg) from None
                else:
                    # raise ValueError exception if a list field is not in list format
                    msg = (
                        f"A field you are trying to populate ('{field}') "
                        "must be a list, but you provided a value of type: "
                        f"{type(field_value).__name__}. For your convenience, "
                        f"the list fields in this table include: "
                        f"{self.list_fields!s}."
                    )
                    raise ValueError(msg)

        super().save(*args, **kwargs)

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)

        # Deserialize the JSON strings back to lists
        for field in cls.list_fields:
            if getattr(instance, field):
                setattr(instance, field, json.loads(getattr(instance, field)))
        return instance


class TemporaryZipFile(BaseModel):
    """
    Model to track temporary zip files created for email downloads.

    These files are automatically cleaned up after a certain period.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        related_name="temporary_zip_files",
        on_delete=models.PROTECT,
    )
    file_path = models.CharField(max_length=500)
    filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField()
    files_processed = models.IntegerField()
    expires_at = models.DateTimeField()
    is_downloaded = models.BooleanField(default=False)
    downloaded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.filename} ({self.owner.email if self.owner else 'No owner'})"

    def save(self, *args, **kwargs):
        # Set expiration time if not already set (default: 7 days)
        if not self.expires_at:
            self.expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
                days=3
            )

        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        """Check if the file has expired and should be deleted."""
        return datetime.datetime.now(datetime.UTC) > self.expires_at

    @property
    def download_url(self) -> str:
        """Generate the download URL for this file."""
        from django.conf import settings

        # Get the site domain from settings, with fallback
        site_domain = settings.SITE_DOMAIN

        # Use HTTPS if available, otherwise HTTP
        protocol = "https" if settings.USE_HTTPS else "http"

        return f"{protocol}://{site_domain}/users/temporary-zip/{self.uuid}/download/"

    def mark_downloaded(self):
        """Mark the file as downloaded."""
        self.is_downloaded = True
        self.downloaded_at = datetime.datetime.now(datetime.UTC)
        self.save(update_fields=["is_downloaded", "downloaded_at"])

    def delete_file(self):
        """Delete the actual file from disk."""
        try:
            file_path = Path(self.file_path)
            if file_path.exists():
                file_path.unlink()
                self.soft_delete()
                return True
        except OSError:
            pass
        return False


class UserSharePermission(BaseModel):
    """
    Model to handle user share permissions for different item types.

    This model generalizes the sharing mechanism to work with both datasets and
    captures, and can be extended to other item types in the future.
    """

    ITEM_TYPE_CHOICES = [
        (ItemType.DATASET, "Dataset"),
        (ItemType.CAPTURE, "Capture"),
    ]

    class PermissionType(models.TextChoices):
        """Enumeration of permission types."""

        VIEW = "view", "View"

    # The user who owns the item being shared
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_share_permissions",
    )

    # The user who is being granted access
    shared_with = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_share_permissions",
    )

    # The type of item being shared
    item_type = models.CharField(
        max_length=20,
        choices=ITEM_TYPE_CHOICES,
    )

    # The UUID of the item being shared (either dataset or capture)
    item_uuid = models.UUIDField()

    # Optional message from the owner when sharing
    message = models.TextField(blank=True)

    # Whether the shared user has been notified
    notified = models.BooleanField(default=False)

    # Whether this share permission is currently active
    is_enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = ["owner", "shared_with", "item_type", "item_uuid"]
        indexes = [
            models.Index(fields=["item_type", "item_uuid"]),
            models.Index(fields=["shared_with", "item_type"]),
            models.Index(fields=["owner", "item_type"]),
        ]

    def __str__(self) -> str:
        return (
            f"{self.owner.email} shared {self.item_type} {self.item_uuid} "
            f"with {self.shared_with.email}"
        )

    @property
    def item(self):
        """Get the actual item object based on item_type and item_uuid."""
        if self.item_type == ItemType.DATASET:
            return Dataset.objects.filter(uuid=self.item_uuid).first()
        if self.item_type == ItemType.CAPTURE:
            return Capture.objects.filter(uuid=self.item_uuid).first()
        return None

    @classmethod
    def get_shared_items_for_user(cls, user, item_type=None):
        """Get all items shared with a user, optionally filtered by item type."""
        queryset = cls.objects.filter(
            shared_with=user,
            is_deleted=False,
            is_enabled=True,
        )
        if item_type:
            queryset = queryset.filter(item_type=item_type)
        return queryset

    @classmethod
    def get_shared_users_for_item(cls, item_uuid, item_type):
        """Get all users who have been shared a specific item."""
        return cls.objects.filter(
            item_uuid=item_uuid,
            item_type=item_type,
            is_deleted=False,
            is_enabled=True,
        ).select_related("shared_with")


def _extract_drf_capture_props(
    capture_props: dict[str, Any],
    center_frequency: float | None = None,
    sample_rate: float | None = None,
    capture_uuid: str | None = None,
) -> tuple[float | None, float | None]:
    """Extracts DRF-specific frequency properties.

    Returns:
        center_frequency and sample_rate
    """
    if not center_frequency:
        center_frequency = _extract_drf_center_frequency(capture_props=capture_props)
    if not sample_rate:
        sample_rate = _extract_drf_sample_rate(capture_props=capture_props)

    # if still no center_frequency, log warning but continue
    if not center_frequency:
        log.warning(
            "No center frequency found for DRF capture %s",
            capture_uuid,
        )

    return center_frequency, sample_rate


def _extract_drf_center_frequency(
    capture_props: dict[str, Any],
) -> float | None:
    """Best effort to extract the center frequency from capture props.

    Args:
        capture_props:      The properties of the capture.
    Returns:
        float | None:       The extracted center frequency in Hz, or None if not found.
    """
    center_frequency = cast("float", capture_props.get("center_freq"))
    if not center_frequency:
        center_frequency = cast("float", capture_props.get("center_frequency"))
    if not center_frequency:
        center_frequencies = cast(
            "list[float]", capture_props.get("center_frequencies")
        )
        if center_frequencies and hasattr(center_frequencies, "__getitem__"):
            center_frequency = center_frequencies[0]
    return center_frequency


def _extract_drf_sample_rate(capture_props: dict[str, Any]) -> float | None:
    """Best effort to extract the sample rate from capture props.

    Args:
        capture_props:      The properties of the capture.
    Returns:
        float | None:       The extracted sample rate in Hz, or None if not found.
    """
    numerator = capture_props.get("sample_rate_numerator")
    denominator = capture_props.get("sample_rate_denominator")
    sample_rate = None
    if numerator and denominator and denominator != 0:
        # try sample_rate_numerator/denominator first
        sample_rate = numerator / denominator
        log.info(
            "Calculated DRF sample_rate: %s/%s = %s",
            numerator,
            denominator,
            sample_rate,
        )
    elif capture_props.get("samples_per_second"):
        # fallback to samples_per_second if numerator/denominator missing
        sample_rate = capture_props.get("samples_per_second")
        log.info("Using DRF samples_per_second: %s", sample_rate)
    return sample_rate


def _extract_radiohound_capture_props(
    capture_props: dict[str, Any],
    center_frequency: float | None,
    sample_rate: float | None,
):
    """Extract RadioHound-specific frequency properties.

    Returns:
        center_frequency and sample_rate
    """
    # For RH: direct fields
    if not center_frequency:
        center_frequency = capture_props.get("center_frequency")
    if not sample_rate:
        sample_rate = capture_props.get("sample_rate")

    return center_frequency, sample_rate


def _group_captures_by_type(
    captures: QuerySet["Capture"],
) -> dict[str, list["Capture"]]:
    """Group captures by capture type for separate queries."""
    captures_by_type: dict[str, list[Capture]] = {}
    for capture in captures:
        capture_type = capture.capture_type
        if capture_type not in captures_by_type:
            captures_by_type[capture_type] = []
        captures_by_type[capture_type].append(capture)
    return captures_by_type


def _query_capture_type_metadata(
    client: Any,
    capture_type: CaptureType | str,
    type_captures: list["Capture"],
) -> dict[str, dict[str, Any]]:
    """Query OpenSearch for metadata of captures of a specific type."""
    uuids = [str(capture.uuid) for capture in type_captures]

    query = {
        "query": {"ids": {"values": uuids}},
        "_source": ["search_props", "capture_props"],
    }

    # Handle both enum objects and string values
    if hasattr(capture_type, "value"):
        index_name = f"captures-{capture_type.value}"
    else:
        index_name = f"captures-{capture_type}"

    response = client.search(index=index_name, body=query, size=len(uuids))

    frequency_data = {}
    # Map results back to capture UUIDs
    for hit in response["hits"]["hits"]:
        capture_uuid = hit["_id"]
        search_props = hit["_source"].get("search_props", {})
        capture_props = hit["_source"].get("capture_props", {})

        frequency_data[capture_uuid] = _extract_bulk_frequency_data(
            capture_type=capture_type,
            search_props=search_props,
            capture_props=capture_props,
            capture_uuid=capture_uuid,
        )

    return frequency_data


def _extract_bulk_frequency_data(
    capture_type: CaptureType | str,
    search_props: dict[str, Any],
    capture_props: dict[str, Any],
    capture_uuid: str,
):
    """Extract frequency data from search_props and capture_props."""
    # Try search_props first (preferred)
    center_frequency = search_props.get("center_frequency")
    sample_rate = search_props.get("sample_rate")

    # If search_props missing, try to read from capture_props directly
    if not center_frequency or not sample_rate:
        if capture_type == CaptureType.DigitalRF:
            center_frequency, sample_rate = _extract_drf_capture_props(
                capture_props=capture_props,
                center_frequency=center_frequency,
                sample_rate=sample_rate,
                capture_uuid=capture_uuid,
            )
        elif capture_type == CaptureType.RadioHound:
            center_frequency, sample_rate = _extract_radiohound_capture_props(
                capture_props=capture_props,
                center_frequency=center_frequency,
                sample_rate=sample_rate,
            )

    return {
        "center_frequency": center_frequency,
        "sample_rate": sample_rate,
        "frequency_min": search_props.get("frequency_min"),
        "frequency_max": search_props.get("frequency_max"),
    }


def user_has_access_to_item(user, item_uuid, item_type):
    """
    Check if a user has access to an item (either as owner or shared user).

    Args:
        user: The user to check access for
        item_uuid: UUID of the item
        item_type: Type of item (e.g., "dataset", "capture")

    Returns:
        bool: True if user has access, False otherwise
    """
    # Map item types to their corresponding models
    item_models = {
        ItemType.DATASET: Dataset,
        ItemType.CAPTURE: Capture,
        # Easy to add new item types here
        # ItemType.FILE: File,
    }

    # Check if user is the owner
    if item_type in item_models:
        model_class = item_models[item_type]
        if model_class.objects.filter(
            uuid=item_uuid, owner=user, is_deleted=False
        ).exists():
            return True

    # Check if user has been shared the item
    return UserSharePermission.objects.filter(
        item_uuid=item_uuid,
        item_type=item_type,
        shared_with=user,
        is_deleted=False,
        is_enabled=True,
    ).exists()


def get_shared_users_for_item(item_uuid, item_type):
    """
    Get all users who have been shared a specific item.

    Args:
        item_uuid: UUID of the item
        item_type: Type of item (e.g., "dataset" or "capture")

    Returns:
        QuerySet: Users who have been shared the item
    """
    return UserSharePermission.get_shared_users_for_item(item_uuid, item_type)


def get_shared_items_for_user(user, item_type=None):
    """
    Get all items shared with a user, optionally filtered by item type.

    Args:
        user: The user to get shared items for
        item_type: Optional item type filter (e.g., "dataset" or "capture")

    Returns:
        QuerySet: UserSharePermission objects for items shared with the user
    """
    return UserSharePermission.get_shared_items_for_user(user, item_type)


@receiver(post_save, sender=Capture)
def handle_capture_soft_delete(sender, instance: Capture, **kwargs) -> None:
    """
    Handle soft deletion of captures by also
    soft deleting related share permissions.
    """
    if instance.is_deleted:
        # This is a soft delete, so we need to soft delete related share permissions
        # Soft delete all UserSharePermission records for this capture
        share_permissions = UserSharePermission.objects.filter(
            item_uuid=instance.uuid,
            item_type=ItemType.CAPTURE,
            is_deleted=False,
        )

        for permission in share_permissions:
            permission.soft_delete()


@receiver(post_save, sender=Dataset)
def handle_dataset_soft_delete(sender, instance: Dataset, **kwargs) -> None:
    """
    Handle soft deletion of datasets by also
    soft deleting related share permissions.
    """
    if instance.is_deleted:
        # This is a soft delete, so we need to soft delete related share permissions
        # Soft delete all UserSharePermission records for this dataset
        share_permissions = UserSharePermission.objects.filter(
            item_uuid=instance.uuid,
            item_type=ItemType.DATASET,
            is_deleted=False,
        )

        for permission in share_permissions:
            permission.soft_delete()
