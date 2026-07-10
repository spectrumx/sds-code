"""Describes the models for the API methods."""

import datetime
import json
import threading
import uuid
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import cast

from blake3 import blake3 as Blake3  # noqa: N812
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.signals import request_started
from django.db import models
from django.db.models import Count
from django.db.models import ProtectedError
from django.db.models import Q
from django.db.models import QuerySet
from django.db.models import Sum
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.template.defaultfilters import slugify
from loguru import logger as log

from .utils.opensearch_client import get_opensearch_client

if TYPE_CHECKING:
    from sds_gateway.users.models import User

# Thread-local storage for request-scoped OpenSearch metadata cache.
# Used as a safety net in get_opensearch_metadata() when the per-instance
# cache (_opensearch_metadata_cache) is missing (e.g. on fresh model
# instances created by get_capture()'s list(related_captures)).
_request_cache = threading.local()


def _clear_request_cache(sender, **kwargs):
    """Clear thread-local OpenSearch metadata cache at start of each request."""
    for attr in ("opensearch_metadata",):
        if hasattr(_request_cache, attr):
            delattr(_request_cache, attr)


request_started.connect(_clear_request_cache, weak=False)

DRF_RF_FILENAME_REGEX_STR = r"^rf@\d+\.\d+\.h5$"


class KeywordNameField(models.CharField):
    """
    Custom field that auto-slugifies keyword names for consistency.
    Enforces lowercase, converts spaces to hyphens, removes non-printable chars.
    """

    def get_prep_value(self, value):
        """Convert the value to a slug before saving to database."""
        value = super().get_prep_value(value)
        if value is None:
            return value
        if not isinstance(value, str):
            msg = "Name attribute must be a string"
            raise TypeError(msg)
        # Slugify the value (lowercase, hyphens instead of spaces, etc.)
        return slugify(value)


class CaptureType(StrEnum):
    """The type of radiofrequency capture."""

    DigitalRF = "drf"
    RadioHound = "rh"
    SigMF = "sigmf"


class CaptureOrigin(StrEnum):
    """The origin of the capture."""

    System = "system"
    User = "user"


class KeySources(StrEnum):
    """The source of an SDS API key."""

    SDSWebUI = "sds_web_ui"
    SVIBackend = "svi_backend"
    SVIWebUI = "svi_web_ui"
    FederationSync = "federation_sync"


class ItemType(StrEnum):
    """The type of item that can be shared."""

    DATASET = "dataset"
    CAPTURE = "capture"
    FILE = "file"

    def pluralize(self) -> str:
        """Get the plural form of the item type."""
        return self.value + "s"


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


class ZipFileStatus(StrEnum):
    """The status of a zip file."""

    Pending = "pending"
    Created = "created"
    Failed = "failed"


class DatasetStatus(StrEnum):
    """The status of a dataset."""

    DRAFT = "draft"
    FINAL = "final"


class PermissionLevel(StrEnum):
    """The access level of a user."""

    OWNER = "owner"
    CO_OWNER = "co-owner"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"


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
    size = models.BigIntegerField(blank=True)
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
        related_name="files_deprecated",
        on_delete=models.SET_NULL,
    )
    capture = models.ForeignKey(
        "Capture",
        blank=True,
        null=True,
        related_name="files_deprecated",
        on_delete=models.SET_NULL,
    )
    datasets = models.ManyToManyField(
        "Dataset",
        blank=True,
        related_name="files",
    )
    captures = models.ManyToManyField(
        "Capture",
        blank=True,
        related_name="files",
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
    from sds_gateway.api_methods.utils.asset_access_control import (  # noqa: PLC0415
        get_connected_asset_ids,
    )

    connected_asset_ids = get_connected_asset_ids(
        item_uuid=instance.uuid,
        item_type=ItemType.FILE,
    )

    associations: list[str] = []
    if instance.capture and not instance.capture.is_deleted:
        associations.append(f"capture ({instance.capture.uuid})")
    if connected_asset_ids["captures"]:
        associations.append(
            f"captures ({len(connected_asset_ids['captures'])}): "
            f"{', '.join(map(str, connected_asset_ids['captures']))}"
        )
    if instance.dataset and not instance.dataset.is_deleted:
        associations.append(f"dataset ({instance.dataset.uuid})")
    if connected_asset_ids["datasets"]:
        associations.append(
            f"datasets ({len(connected_asset_ids['datasets'])}): "
            f"{', '.join(map(str, connected_asset_ids['datasets']))}"
        )

    if not associations:
        return

    msg = (
        f"Cannot delete file '{instance.name}': it is "
        f"associated with {' and '.join(associations)}."
        " Delete (or remove from) the associated object(s) first."
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
        related_name="captures_deprecated",
        on_delete=models.SET_NULL,
    )
    datasets = models.ManyToManyField(
        "Dataset",
        blank=True,
        related_name="captures",
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
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> tuple[int, dict[str, int]]:
        """Hard delete this record after checking for blockers."""
        raise_if_capture_deletion_is_blocked(instance=self)
        return super().delete(*args, **kwargs)

    def soft_delete(self) -> None:
        """Soft delete this record after checking for blockers."""
        from sds_gateway.api_methods.utils.asset_access_control import (  # noqa: PLC0415
            disconnect_assets,
        )

        raise_if_capture_deletion_is_blocked(instance=self)
        disconnect_assets(item=self, item_type=ItemType.CAPTURE)
        return super().soft_delete()

    @property
    def center_frequency_ghz(self) -> float | None:
        """Get center frequency in GHz from OpenSearch."""
        opensearch_metadata = self.get_opensearch_metadata()
        center_freq_hz = opensearch_metadata.get("center_frequency")
        if center_freq_hz:
            return center_freq_hz / 1e9
        return None

    @property
    def sample_rate_mhz(self) -> float | None:
        """Get sample rate in MHz from OpenSearch."""
        opensearch_metadata = self.get_opensearch_metadata()
        sample_rate_hz = opensearch_metadata.get("sample_rate")
        if sample_rate_hz:
            return sample_rate_hz / 1e6
        return None

    @property
    def start_time(self) -> int | None:
        """Get the start time of the capture in unix seconds."""
        return self.get_opensearch_metadata().get("start_time")

    @property
    def end_time(self) -> int | None:
        """Get the end time of the capture in unix seconds."""
        return self.get_opensearch_metadata().get("end_time")

    @property
    def file_cadence(self) -> int | None:
        """Get the file cadence of the capture in milliseconds."""
        return self.get_opensearch_metadata().get("file_cadence")

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
        return cast(
            "str",
            dict(self.CAPTURE_TYPE_CHOICES).get(self.capture_type, self.capture_type),
        )

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

        capture_list = list(related_captures)
        if len(capture_list) <= 1:
            # Only one capture found, return as single capture
            return {"capture": self, "is_composite": False}

        # Multiple captures found, create composite
        return {
            "captures": capture_list,
            "is_composite": True,
            "top_level_dir": self.top_level_dir,
            "capture_type": self.capture_type,
            "owner": self.owner,
        }

    def get_drf_data_files_queryset(self) -> QuerySet[File]:
        """DRF data files (rf@*.h5) for this capture (M2M + FK)."""
        from sds_gateway.api_methods.utils.relationship_utils import (  # noqa: PLC0415
            get_capture_files,
        )

        if self.capture_type != CaptureType.DigitalRF:
            log.warning(f"Capture {self.uuid} is not a DigitalRF capture")
            return File.objects.none()

        return get_capture_files(self, include_deleted=False).filter(
            name__regex=DRF_RF_FILENAME_REGEX_STR,
        )

    def get_drf_data_files_stats(self) -> dict[str, int]:
        """
        Count + total size in one query; cached per instance.

        File primary key is ``uuid``; use ``pk`` in aggregates.
        """
        if hasattr(self, "_drf_data_files_stats_cache"):
            return self._drf_data_files_stats_cache

        qs = self.get_drf_data_files_queryset()
        agg = qs.aggregate(total_count=Count("pk"), total_size=Sum("size"))
        self._drf_data_files_stats_cache = {
            "total_count": agg["total_count"] or 0,
            "total_size": int(agg["total_size"] or 0),
        }
        return self._drf_data_files_stats_cache

    def get_capture_files_stats(self) -> dict[str, int]:
        """
        Count + total size for all files linked to this capture (any type).

        Cached per instance.
        """
        if hasattr(self, "_capture_files_stats_cache"):
            return self._capture_files_stats_cache

        from sds_gateway.api_methods.utils.relationship_utils import (  # noqa: PLC0415
            get_capture_files,
        )

        qs = get_capture_files(self, include_deleted=False)
        agg = qs.aggregate(total_count=Count("pk"), total_size=Sum("size"))
        self._capture_files_stats_cache = {
            "total_count": agg["total_count"] or 0,
            "total_size": int(agg["total_size"] or 0),
        }
        return self._capture_files_stats_cache

    def get_files_summary(self) -> dict[str, Any]:
        """
        Unified file summary for API/UI (all capture types).

        Cached per instance. DRF captures include a ``data_files`` subset.
        """
        if hasattr(self, "_files_summary_cache"):
            return self._files_summary_cache

        all_stats = self.get_capture_files_stats()
        summary: dict[str, Any] = {
            "total_count": all_stats["total_count"],
            "total_size": all_stats["total_size"],
        }

        if self.capture_type == CaptureType.DigitalRF:
            drf = self.get_drf_data_files_stats()
            count = drf["total_count"]
            size = drf["total_size"]
            summary["data_files"] = {
                "count": count,
                "total_size": size,
                "per_data_file_size": (float(size) / count) if count else None,
            }
            if summary["total_size"] < size:
                log.warning(
                    f"Capture {self.uuid}: total_size ({summary['total_size']}) "
                    f"< data_files total_size ({size}); "
                    "using data total."
                )
                summary["total_size"] = size

        self._files_summary_cache = summary
        return self._files_summary_cache

    def get_opensearch_metadata(self) -> dict[str, Any]:
        """
        Query OpenSearch for frequency metadata for this specific capture.

        The result is cached on the instance (``_opensearch_metadata_cache``) so
        repeated access from properties and serializers reuses a single
        response within the lifetime of this ``Capture`` object.

        Returns:
            dict: Frequency metadata (center_frequency, sample_rate, etc.)
        """
        if hasattr(self, "_opensearch_metadata_cache"):
            log.trace(f"meta_cache HIT for {self.uuid}")
            return self._opensearch_metadata_cache

        # Fallback: thread-local cache (populated by set_bulk_metadata_cache).
        # Catches fresh model instances (e.g. from get_capture() →
        # list(related_captures)) that don't share the original queryset
        # instance identity.
        tl = getattr(_request_cache, "opensearch_metadata", None)
        if tl is not None:
            cached = tl.get(str(self.uuid))
            if cached is not None:
                log.trace(f"meta_cache thread-local HIT for {self.uuid}")
                self._opensearch_metadata_cache = cached
                return cached

        log.trace(f"meta_cache MISS for {self.uuid}")

        result: dict[str, Any] = {}
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

            log.debug(
                f"Querying OpenSearch index '{index_name}' for capture {self.uuid}"
            )

            response = client.search(
                index=index_name,
                body=query,
                size=1,  # pyright: ignore[reportCallIssue]
            )

            if response["hits"]["total"]["value"] > 0:
                source = response["hits"]["hits"][0]["_source"]
                result = self._extract_metadata_from_source(source)
            else:
                log.warning(f"No OpenSearch data found for capture {self.uuid}")

        except Exception:  # noqa: BLE001
            log.exception(f"Error querying OpenSearch for capture {self.uuid}")

        self._opensearch_metadata_cache = result
        return self._opensearch_metadata_cache

    def _extract_metadata_from_source(self, source: dict[str, Any]) -> dict[str, Any]:
        """Extract frequency metadata from OpenSearch source data."""

        search_props = source.get("search_props", {})
        log.debug(f"OpenSearch data for {self.uuid}: search_props={search_props}")

        # Try search_props first (preferred)
        center_frequency = search_props.get("center_frequency")
        sample_rate = search_props.get("sample_rate")
        file_cadence = self._extract_drf_file_cadence_from_search_props(search_props)

        # If search_props missing, try to read from capture_props directly
        if not center_frequency or not sample_rate:
            capture_props = source.get("capture_props", {})
            log.info(
                f"search_props incomplete, checking capture_props: "
                f"{list(capture_props.keys())}"
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
            "start_time": search_props.get("start_time", None),
            "end_time": search_props.get("end_time", None),
            "file_cadence": file_cadence,
        }

    def _extract_drf_file_cadence_from_search_props(
        self, search_props: dict[str, Any]
    ) -> int | None:
        """Extract file cadence (in milliseconds) from OpenSearch source data."""
        count = self.get_drf_data_files_stats()["total_count"]
        start_time = search_props.get("start_time")
        end_time = search_props.get("end_time")

        if start_time is None or end_time is None:
            log.warning(f"Start or end time not found for DRF capture {self.uuid}")
            return None

        if count == 0:
            return None

        duration_sec = end_time - start_time
        duration_ms = duration_sec * 1000
        return max(1, int(duration_ms / count))

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

        except Exception:  # noqa: BLE001
            log.exception("Error bulk loading frequency metadata")
            return {}
        else:
            return frequency_data

    @classmethod
    def set_bulk_metadata_cache(
        cls, captures: list["Capture"], metadata: dict[str, dict[str, Any]]
    ) -> None:
        """Attach bulk-loaded metadata to each capture instance.

        Sets ``_opensearch_metadata_cache`` on each capture so that
        ``get_opensearch_metadata()`` returns early without an additional
        OpenSearch round-trip.

        Args:
            captures: List of Capture instances to attach metadata to.
            metadata: Mapping from ``uuid_str`` to metadata dict
                      (as returned by ``bulk_load_frequency_metadata``).
        """
        # Clear any stale thread-local data before setting fresh data
        if hasattr(_request_cache, "opensearch_metadata"):
            del _request_cache.opensearch_metadata

        loaded = 0
        missing = 0
        for capture in captures:
            cache_key = str(capture.uuid)
            if cache_key in metadata:
                capture._opensearch_metadata_cache = metadata[cache_key]  # noqa: SLF001
                loaded += 1
            else:
                missing += 1
                capture._opensearch_metadata_cache = {}  # noqa: SLF001

        # Also store in thread-local cache so fresh instances (e.g. from
        # get_capture() → list(related_captures)) can still find their
        # metadata without an individual round-trip.
        _request_cache.opensearch_metadata = metadata

        log.debug(
            f"set_bulk_metadata_cache: loaded={loaded}, missing={missing}, "
            f"total={len(captures)}"
        )

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
            log.debug(f"Index: {index_name}")
            log.debug(f"UUID: {self.uuid}")
            log.debug(f"Query: {query}")

            response = client.search(
                index=index_name,
                body=query,
                size=1,  # pyright: ignore[reportCallIssue]
            )

            log.debug("=== DEBUG: OpenSearch Response ===")
            log.debug(f"Total hits: {response['hits']['total']['value']}")

            if response["hits"]["total"]["value"] > 0:
                source = response["hits"]["hits"][0]["_source"]
                log.debug("=== DEBUG: Full Source Data ===")
                log.debug(f"Source keys: {list(source.keys())}")

                search_props = source.get("search_props", {})
                log.debug("=== DEBUG: search_props ===")
                log.debug(f"search_props keys: {list(search_props.keys())}")
                log.debug(f"search_props content: {search_props}")

                capture_props = source.get("capture_props", {})
                log.debug("=== DEBUG: capture_props ===")
                log.debug(f"capture_props keys: {list(capture_props.keys())}")
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
                            log.debug(f"capture_props.{field} = {capture_props[field]}")

                return source
        except Exception:  # noqa: BLE001
            log.exception("=== DEBUG: Exception occurred ===")
            log.exception("Error occurred during frequency metadata extraction")
            return None
        else:
            log.debug("=== DEBUG: No data found ===")
            return None


def raise_if_capture_deletion_is_blocked(instance: Capture) -> None:
    """Raises an error if the file passed can't be deleted.

    Raises:
        ProtectedError if the capture is associated with a dataset.
    """
    from sds_gateway.api_methods.utils.asset_access_control import (  # noqa: PLC0415
        get_connected_asset_ids,
    )

    connected_asset_ids = get_connected_asset_ids(
        item_uuid=instance.uuid,
        item_type=ItemType.CAPTURE,
    )

    associations: list[str] = []
    # Note: deprecated FK relationship is not checked here
    # since data is already migrated and we are just returning related assets.
    if connected_asset_ids["datasets"]:
        associations.append(
            f"datasets ({len(connected_asset_ids['datasets'])}): "
            f"{', '.join(map(str, connected_asset_ids['datasets']))}"
        )

    if not associations:
        return

    msg = (
        f"Cannot delete capture '{instance.name}': it is "
        f"associated with {' and '.join(associations)}."
        " Delete the associated object(s) first or "
        "remove the capture from the datasets it is part of."
    )
    raise ProtectedError(msg, protected_objects={instance})


@receiver(pre_delete, sender=Capture)
def prevent_capture_deletion(sender, instance: Capture, **kwargs) -> None:
    """Prevents deletion of captures associated with datasets.

    Version to cover bulk deletions from querysets.
    """
    raise_if_capture_deletion_is_blocked(instance=instance)


class Keyword(BaseModel):
    """
    Model for user-entered keywords that can be associated with datasets.
    Keywords can be associated with multiple datasets via ManyToManyField.

    The name field is auto-slugified and serves as the primary key,
    enforcing uniqueness and immutability after creation.
    """

    # Override the uuid primary key from BaseModel
    uuid = models.UUIDField(default=uuid.uuid4, editable=False)

    name = KeywordNameField(
        max_length=255,
        primary_key=True,
        help_text=(
            "The keyword slug (auto-slugified, e.g., 'RF Spectrum' → 'rf-spectrum')"
        ),
    )
    datasets = models.ManyToManyField(
        "Dataset",
        related_name="keywords",
        help_text="The datasets this keyword is associated with",
    )

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        ordering = ["name"]
        verbose_name = "Keyword"
        verbose_name_plural = "Keywords"

    def __str__(self) -> str:
        return self.name


class DatasetQuerySet(QuerySet["Dataset"]):
    def federation_exportable(self) -> QuerySet:
        return self.filter(
            status=DatasetStatus.FINAL,
            is_public=True,
            is_deleted=False,
        )


DatasetManager = models.Manager.from_queryset(DatasetQuerySet)


class Dataset(BaseModel):
    """
    Model for datasets defined and created through the API.

    Schema Definition: https://github.com/spectrumx/schema-definitions/blob/master/definitions/sds/abstractions/dataset/README.md
    """

    list_fields = ["authors", "institutions"]

    STATUS_CHOICES = [
        (DatasetStatus.DRAFT, "Draft"),
        (DatasetStatus.FINAL, "Final"),
    ]

    name = models.CharField(max_length=255, blank=False, default=None)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=DatasetStatus.DRAFT,
        help_text="The current status of the dataset",
    )
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
    institutions = models.TextField(blank=True)
    release_date = models.DateTimeField(blank=True, null=True)
    repository = models.URLField(blank=True)
    version = models.IntegerField(default=1)
    previous_version = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="next_version",
    )
    website = models.URLField(blank=True)
    provenance = models.JSONField(blank=True, null=True)
    citation = models.JSONField(blank=True, null=True)
    other = models.JSONField(blank=True, null=True)
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="shared_datasets",
    )

    objects = DatasetManager()

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

        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        snapshot = self._published_snapshot_from_db()
        if snapshot is None:
            return

        old_status, old_is_public = snapshot
        if not self._was_final_status(old_status) and not self._was_public(
            is_public=old_is_public,
        ):
            return

        if self._was_final_status(status=old_status) and self.status != old_status:
            msg = "Final datasets cannot be reverted to draft."
            raise ValidationError(msg)

        if (
            self._was_public(is_public=old_is_public)
            and self.is_public != old_is_public
        ):
            msg = "Public datasets cannot be reverted to private."
            raise ValidationError(msg)

    def is_federation_exportable(self) -> bool:
        return (
            not self.is_deleted
            and self.is_public
            and self.status == DatasetStatus.FINAL
        )

    def _published_snapshot_from_db(self) -> tuple[str, bool] | None:
        if not self.pk:
            return None
        return (
            type(self)
            .objects.filter(pk=self.pk)
            .values_list("status", "is_public")
            .first()
        )

    @staticmethod
    def _was_final_status(status: DatasetStatus) -> bool:
        return status == DatasetStatus.FINAL

    @staticmethod
    def _was_public(*, is_public: bool) -> bool:
        return is_public

    def soft_delete(self) -> None:
        """Soft delete this record after checking for blockers."""
        from sds_gateway.api_methods.utils.asset_access_control import (  # noqa: PLC0415
            disconnect_assets,
        )

        disconnect_assets(item=self, item_type=ItemType.DATASET)
        return super().soft_delete()

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)

        # Deserialize the JSON strings back to lists
        for field in cls.list_fields:
            if getattr(instance, field):
                setattr(instance, field, json.loads(getattr(instance, field)))
        return instance

    def get_dataset_file_statistics(self) -> dict[str, int]:
        """
        Aggregate file counts/sizes for this dataset (artifacts + capture files).

        Cached per instance. One queryset pass for totals; separate filters for
        capture-linked vs artifact-only files.
        """
        if hasattr(self, "_dataset_file_statistics_cache"):
            return self._dataset_file_statistics_cache

        from sds_gateway.api_methods.utils.relationship_utils import (  # noqa: PLC0415
            get_dataset_files_including_captures,
        )

        files_qs = get_dataset_files_including_captures(self, include_deleted=False)
        total_files = files_qs.count()
        total_size = int(
            files_qs.aggregate(total=Sum("size"))["total"] or 0,
        )
        captures_count = (
            files_qs.filter(Q(capture__isnull=False) | Q(captures__isnull=False))
            .distinct()
            .count()
        )
        artifacts_count = files_qs.filter(
            capture__isnull=True,
            captures__isnull=True,
        ).count()

        self._dataset_file_statistics_cache = {
            "total_files": total_files,
            "captures": captures_count,
            "artifacts": artifacts_count,
            "total_size": total_size,
        }
        return self._dataset_file_statistics_cache

    def get_files_summary(self) -> dict[str, Any]:
        """Alias for dataset file statistics in API serializers."""
        stats = self.get_dataset_file_statistics()
        return {
            "total_count": stats["total_files"],
            "total_size": stats["total_size"],
            "capture_linked_files": stats["captures"],
            "artifact_files": stats["artifacts"],
        }

    def get_authors_display(self):
        """Get the authors as a list for display purposes."""
        if not self.authors:
            return []

        # from_db should have already converted JSON string to list
        if not isinstance(self.authors, list):
            log.warning(
                f"Dataset {self.uuid}: authors field is not a list "
                f"(type: {type(self.authors).__name__})",
            )
            return []

        # Check if authors are in old string format and need conversion
        if self.authors and isinstance(self.authors[0], str):
            log.warning(
                f"Dataset {self.uuid}: authors still in old string format, "
                f"needs migration",
            )
            # Convert old format for backward compatibility
            return [{"name": author, "orcid_id": ""} for author in self.authors]

        # Authors should already be in new object format
        return self.authors


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
    creation_status = models.CharField(
        max_length=20,
        choices=[(st.value, st.value.title()) for st in ZipFileStatus],
        default=ZipFileStatus.Pending.value,
    )
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

    def mark_failed(self):
        """Mark the file as failed."""
        self.creation_status = ZipFileStatus.Failed.value
        self.save(update_fields=["creation_status"])

    def mark_completed(self):
        """Mark the file as completed."""
        self.creation_status = ZipFileStatus.Created.value
        self.save(update_fields=["creation_status"])

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

    PERMISSION_CHOICES = [
        (PermissionLevel.VIEWER, "Viewer"),
        (PermissionLevel.CONTRIBUTOR, "Contributor"),
        (PermissionLevel.CO_OWNER, "Co-Owner"),
    ]

    # The user who shared the item (owner of the share permission)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owned_share_permissions",
    )

    permission_level = models.CharField(
        max_length=20,
        choices=PERMISSION_CHOICES,
        default=PermissionLevel.VIEWER,
    )

    # The user who is being granted access
    shared_with = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="received_share_permissions",
    )

    share_groups = models.ManyToManyField(
        "ShareGroup",
        blank=True,
        related_name="group_share_permissions",
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

    # Whether this permission was explicitly granted to the user individually,
    # as opposed to being created solely via a group share. When True, revocation
    # of every group still keeps the permission active.
    is_individual_share = models.BooleanField(default=True)

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
            f"with {self.shared_with.email if self.shared_with else 'N/A'} "
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
    def get_shared_items_for_user(
        cls, user: "User", item_type: str | None = None
    ) -> QuerySet["UserSharePermission"]:
        """Get all items shared with a user, optionally filtered by item type."""
        queryset = cast(
            "QuerySet[UserSharePermission]",
            cls.objects.filter(
                shared_with=user,
                is_deleted=False,
                is_enabled=True,
            ),
        )
        if item_type:
            queryset = queryset.filter(item_type=item_type)
        return queryset

    def has_access_through_groups(self) -> bool:
        """Check if user still has access through any group."""
        return self.share_groups.filter(is_deleted=False).exists()

    def update_enabled_status(self) -> None:
        """Update enabled status based on individual and group access."""
        self.is_enabled = self.is_individual_share or self.share_groups.exists()
        self.save()

    @classmethod
    def get_shared_users_for_item(
        cls, item_uuid: uuid.UUID, item_type: str
    ) -> QuerySet["UserSharePermission"]:
        """Get all users who have been shared a specific item."""
        return cast(
            "QuerySet[UserSharePermission]",
            cls.objects.filter(
                item_uuid=item_uuid,
                item_type=item_type,
                is_deleted=False,
                is_enabled=True,
            ).select_related("shared_with"),
        )

    @classmethod
    def get_user_permission_level(
        cls, user: "User", item_uuid: uuid.UUID, item_type: str
    ) -> str | None:
        """
        Get the permission level for a user on a specific item.

        Args:
            user: The user to check permissions for
            item_uuid: UUID of the item
            item_type: Type of item (e.g., "dataset", "capture")

        Returns:
            str: Permission level ("owner", "co-owner", "contributor", "viewer",
                or None if no access)
        """
        # Check if user is the owner
        item_models = {
            ItemType.DATASET: Dataset,
            ItemType.CAPTURE: Capture,
        }

        if item_type in item_models:
            model_class = item_models[ItemType(item_type)]
            if model_class.objects.filter(
                uuid=item_uuid, owner=user, is_deleted=False
            ).exists():
                return PermissionLevel.OWNER

        # Check shared permissions
        permission = cls.objects.filter(
            item_uuid=item_uuid,
            item_type=item_type,
            shared_with=user,
            is_deleted=False,
            is_enabled=True,
        ).first()

        if permission:
            return permission.permission_level

        return None

    @classmethod
    def user_can_view(cls, user: "User", item_uuid: uuid.UUID, item_type: str) -> bool:
        """Check if user can view the item."""
        return cls.get_user_permission_level(user, item_uuid, item_type) is not None

    @classmethod
    def user_can_add_assets(
        cls, user: "User", item_uuid: uuid.UUID, item_type: str
    ) -> bool:
        """Check if user can add assets to the item."""
        permission_level = cls.get_user_permission_level(user, item_uuid, item_type)
        return permission_level in [
            PermissionLevel.OWNER,
            PermissionLevel.CO_OWNER,
            PermissionLevel.CONTRIBUTOR,
        ]

    @classmethod
    def user_can_remove_assets(
        cls, user: "User", item_uuid: uuid.UUID, item_type: str
    ) -> bool:
        """Check if user can remove assets from the item."""
        permission_level = cls.get_user_permission_level(user, item_uuid, item_type)
        return permission_level in [
            PermissionLevel.OWNER,
            PermissionLevel.CO_OWNER,
        ]

    @classmethod
    def user_can_edit_dataset(
        cls, user: "User", item_uuid: uuid.UUID, item_type: str
    ) -> bool:
        """Check if user can edit dataset metadata (name, description)."""
        if item_type != ItemType.DATASET:
            return False
        permission_level = cls.get_user_permission_level(user, item_uuid, item_type)
        return permission_level in [
            PermissionLevel.OWNER,
            PermissionLevel.CO_OWNER,
        ]

    @classmethod
    def user_can_remove_others_assets(
        cls, user: "User", item_uuid: uuid.UUID, item_type: str
    ) -> bool:
        """Check if user can remove assets owned by other users."""
        permission_level = cls.get_user_permission_level(user, item_uuid, item_type)
        return permission_level in [
            PermissionLevel.OWNER,
            PermissionLevel.CO_OWNER,
        ]

    @classmethod
    def user_can_share(cls, user: "User", item_uuid: uuid.UUID, item_type: str) -> bool:
        """Check if user can share the item with others."""
        permission_level = cls.get_user_permission_level(user, item_uuid, item_type)
        return permission_level in [
            PermissionLevel.OWNER,
            PermissionLevel.CO_OWNER,
        ]

    @classmethod
    def user_can_advance_version(
        cls, user: "User", item_uuid: uuid.UUID, item_type: str
    ) -> bool:
        """Check if user can advance the version of the item."""
        permission_level = cls.get_user_permission_level(user, item_uuid, item_type)
        return permission_level in [
            PermissionLevel.OWNER,
            PermissionLevel.CO_OWNER,
        ]


class DEPRECATEDPostProcessedData(BaseModel):
    """
    Generalized model to store post-processed data for captures.

    This model can store any type of post-processed data (waterfall, spectrogram, etc.)
    and tracks processing status and metadata.
    """

    capture = models.ForeignKey(
        "Capture",
        on_delete=models.CASCADE,
        related_name="post_processed_data",
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
        choices=[(ps.value, ps.value.title()) for ps in ProcessingStatus],
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
        unique_together = ["capture", "processing_type", "processing_parameters"]
        ordering = ["-created_at"]
        verbose_name_plural = "Post processed data (deprecated)"
        indexes = [
            models.Index(fields=["capture", "processing_type"]),
            models.Index(fields=["processing_status"]),
            models.Index(fields=["pipeline_id"]),
        ]

    def __str__(self) -> str:
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
            self.data_file.save(filename, File(f), save=False)
        self.save(update_fields=["data_file"])


class ShareGroup(BaseModel):
    """
    Model to handle share groups for datasets and captures.
    """

    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,  # prevents users from being deleted if they own groups (delete the groups first). # noqa: E501
        related_name="owned_share_groups",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="member_share_groups",
    )

    def __str__(self) -> str:
        return f"ShareGroup: {self.name} (Owner: {self.owner.email})"


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
            f"No center frequency found for DRF capture {capture_uuid}",
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
        log.debug(
            f"Calculated DRF sample_rate: {numerator}/{denominator} = {sample_rate}",
        )
    elif capture_props.get("samples_per_second"):
        # fallback to samples_per_second if numerator/denominator missing
        sample_rate = capture_props.get("samples_per_second")
        log.debug(f"Using DRF samples_per_second: {sample_rate}")
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
        "start_time": search_props.get("start_time"),
        "end_time": search_props.get("end_time"),
        "file_cadence": None,  # requires per-capture file count; skip in bulk
    }


def user_has_access_to_item(user: "User", item_uuid: uuid.UUID, item_type: str) -> bool:
    """
    Check if a user has access to an item (either as owner or shared user).

    Args:
        user: The user to check access for
        item_uuid: UUID of the item
        item_type: Type of item (e.g., "dataset", "capture")

    Returns:
        bool: True if user has access, False otherwise
    """
    return UserSharePermission.user_can_view(user, item_uuid, item_type)


def get_user_permission_level(
    user: "User", item_uuid: uuid.UUID, item_type: str
) -> str | None:
    """
    Get the permission level for a user on a specific item.
    """
    return UserSharePermission.get_user_permission_level(user, item_uuid, item_type)


def get_shared_users_for_item(
    item_uuid: uuid.UUID, item_type: str
) -> QuerySet["UserSharePermission"]:
    """
    Get all users who have been shared a specific item.

    Args:
        item_uuid: UUID of the item
        item_type: Type of item (e.g., "dataset" or "capture")

    Returns:
        QuerySet: Users who have been shared the item
    """
    return UserSharePermission.get_shared_users_for_item(item_uuid, item_type)


def get_shared_items_for_user(
    user: "User", item_type: str | None = None
) -> QuerySet["UserSharePermission"]:
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


@receiver(post_save, sender=ShareGroup)
def handle_sharegroup_soft_delete(
    sender: type[ShareGroup], instance: ShareGroup, **kwargs: Any
) -> None:
    """
    Handle soft deletion of share groups by updating related share permissions.
    """
    if instance.is_deleted:
        # Find all UserSharePermission records that include this group
        share_permissions = UserSharePermission.objects.filter(
            share_groups=instance,
            is_deleted=False,
        )

        for permission in share_permissions:
            # Remove the group from the permission
            permission.share_groups.remove(instance)
            # Update the enabled status based on remaining groups
            permission.update_enabled_status()
            permission.save()
