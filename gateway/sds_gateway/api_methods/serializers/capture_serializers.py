"""Capture serializers for the SDS Gateway API methods."""

from datetime import UTC
from datetime import datetime
from typing import Any
from typing import cast

from django.utils import timezone as django_timezone
from drf_spectacular.utils import extend_schema_field
from loguru import logger as log
from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnList

from sds_gateway.api_methods.helpers.index_handling import retrieve_indexed_metadata
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import DEPRECATEDPostProcessedData
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import PermissionLevel
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.serializers.summary_serializers import (
    DatasetSummarySerializer,
)
from sds_gateway.api_methods.serializers.summary_serializers import (
    FileSummarySerializer,
)
from sds_gateway.api_methods.serializers.user_serializer import UserGetSerializer
from sds_gateway.api_methods.serializers.user_serializer import (
    UserSharePermissionSerializer,
)
from sds_gateway.api_methods.utils.asset_access_control import check_if_shared
from sds_gateway.api_methods.utils.relationship_utils import get_capture_datasets
from sds_gateway.api_methods.utils.relationship_utils import get_capture_files


def _epoch_sec_to_iso_utc_z(epoch_sec: int) -> str:
    """Format OpenSearch epoch seconds as an ISO 8601 UTC string with ``Z`` suffix."""
    dt = datetime.fromtimestamp(epoch_sec, tz=UTC)
    return dt.isoformat().replace("+00:00", "Z")


def _epoch_sec_to_local_display(epoch_sec: int) -> str:
    """Human-readable local time (same pattern as ``formatted_created_at``)."""
    dt = datetime.fromtimestamp(epoch_sec, tz=UTC)
    return django_timezone.localtime(dt).strftime("%m/%d/%Y %I:%M:%S %p")


def _channel_row_bounds_from_os_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Map OpenSearch metadata to composite channel serializer fields."""
    entry: dict[str, Any] = {}
    start_sec = meta.get("start_time")
    end_sec = meta.get("end_time")
    entry["capture_start_epoch_sec"] = start_sec
    entry["capture_end_epoch_sec"] = end_sec
    entry["capture_start_iso_utc"] = (
        _epoch_sec_to_iso_utc_z(start_sec) if start_sec is not None else None
    )
    entry["capture_end_iso_utc"] = (
        _epoch_sec_to_iso_utc_z(end_sec) if end_sec is not None else None
    )
    entry["capture_start_display"] = (
        _epoch_sec_to_local_display(start_sec) if start_sec is not None else None
    )
    entry["capture_end_display"] = (
        _epoch_sec_to_local_display(end_sec) if end_sec is not None else None
    )
    if start_sec is None or end_sec is None:
        entry["length_of_capture_ms"] = None
    else:
        entry["length_of_capture_ms"] = (end_sec - start_sec) * 1000
    entry["file_cadence_ms"] = meta.get("file_cadence")
    return entry


class DEPRECATEDPostProcessedDataSerializer(
    serializers.ModelSerializer[DEPRECATEDPostProcessedData]
):
    """Serializer for PostProcessedData model."""

    class Meta:
        model = DEPRECATEDPostProcessedData
        fields = [
            "uuid",
            "capture",
            "processing_type",
            "processing_parameters",
            "data_file",
            "metadata",
            "processing_status",
            "processing_error",
            "processed_at",
            "pipeline_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "uuid",
            "capture",
            "processing_type",
            "processing_parameters",
            "data_file",
            "metadata",
            "processing_status",
            "processing_error",
            "processed_at",
            "pipeline_id",
            "created_at",
            "updated_at",
        ]


class CaptureGetSerializer(serializers.ModelSerializer[Capture]):
    owner = UserGetSerializer()
    share_permissions = serializers.SerializerMethodField()
    is_shared = serializers.SerializerMethodField()
    is_shared_with_me = serializers.SerializerMethodField()
    permission_level = serializers.SerializerMethodField()
    capture_props = serializers.SerializerMethodField()
    files = serializers.SerializerMethodField()
    total_file_count = serializers.SerializerMethodField()
    total_file_size = serializers.SerializerMethodField()
    data_files_info = serializers.SerializerMethodField()
    datasets = serializers.SerializerMethodField()
    center_frequency_ghz = serializers.SerializerMethodField()
    sample_rate_mhz = serializers.SerializerMethodField()
    length_of_capture_ms = serializers.SerializerMethodField()
    file_cadence_ms = serializers.SerializerMethodField()
    capture_start_epoch_sec = serializers.SerializerMethodField()
    capture_start_iso_utc = serializers.SerializerMethodField()
    capture_end_iso_utc = serializers.SerializerMethodField()
    capture_start_display = serializers.SerializerMethodField()
    capture_end_display = serializers.SerializerMethodField()
    formatted_created_at = serializers.SerializerMethodField()
    capture_type_display = serializers.SerializerMethodField()
    post_processed_data = serializers.SerializerMethodField()

    def get_datasets(self, capture: Capture) -> list[dict[str, Any]]:
        """Datasets linked to this capture (summary rows only; avoids nested graphs)."""
        qs = get_capture_datasets(capture, include_deleted=False)
        return DatasetSummarySerializer(qs, many=True, context=self.context or {}).data

    def get_share_permissions(self, capture: Capture) -> list[UserSharePermission]:
        """Get the share permissions for the capture."""
        user_share_permissions = UserSharePermission.objects.filter(
            item_uuid=capture.uuid,
            item_type=ItemType.CAPTURE,
            is_deleted=False,
            is_enabled=True,
        )
        return UserSharePermissionSerializer(user_share_permissions, many=True).data

    def get_is_shared_with_me(self, capture: Capture) -> bool:
        """Get whether the capture is shared with the current user."""
        request = (self.context or {}).get("request")
        if request and hasattr(request, "user"):
            return (
                UserSharePermission.objects.filter(
                    shared_with=request.user,
                    item_type=ItemType.CAPTURE,
                    item_uuid=capture.uuid,
                    is_enabled=True,
                    is_deleted=False,
                )
                .exclude(owner=request.user)
                .exists()
            )
        return False

    def get_is_shared(self, capture: Capture) -> bool:
        """Get whether the capture is shared.

        Returns:
            True if the capture has enabled share permissions, False otherwise.
        """
        return check_if_shared(capture.uuid, ItemType.CAPTURE)

    def get_permission_level(self, capture: Capture) -> PermissionLevel | None:
        """Get the current user's permission level for this capture."""
        request = (self.context or {}).get("request")
        if not request or not hasattr(request, "user"):
            return None

        # Check if user is the owner
        if capture.owner == request.user:
            return PermissionLevel.OWNER

        # Check for shared permissions
        permission = UserSharePermission.objects.filter(
            shared_with=request.user,
            item_type=ItemType.CAPTURE,
            item_uuid=capture.uuid,
            is_enabled=True,
            is_deleted=False,
        ).first()

        return permission.permission_level if permission else None

    def get_files(self, capture: Capture) -> ReturnList[File]:
        """Get the files for the capture.

        Returns:
            A list of serialized file objects with uuid, name, and directory fields.
        """
        exclude_files = (self.context or {}).get("exclude_files", False)
        if exclude_files:
            return []

        non_deleted_files = get_capture_files(capture, include_deleted=False)
        return FileSummarySerializer(
            non_deleted_files, many=True, context=self.context or {}
        ).data

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_total_file_count(self, capture: Capture) -> int:
        """Get the total file count for the capture."""
        return capture.get_files_summary()["total_count"]

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_total_file_size(self, capture: Capture) -> int:
        """Get the total file size of all files associated with this capture."""
        return capture.get_files_summary()["total_size"]

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_data_files_info(self, capture: Capture) -> dict[str, Any]:
        """Get the file summary for the capture (all types; DRF includes data_files)."""
        summary = capture.get_files_summary()
        data_files = summary.get("data_files")
        result: dict[str, Any] = {
            "total_count": summary["total_count"],
            "total_size": summary["total_size"],
        }
        if data_files:
            result["count"] = data_files["count"]
            result["data_files_total_size"] = data_files["total_size"]
            result["per_data_file_size"] = data_files.get("per_data_file_size")
        else:
            result["count"] = summary["total_count"]
        return result

    @extend_schema_field(serializers.FloatField)
    def get_center_frequency_ghz(self, capture: Capture) -> float | None:
        """Get the center frequency in GHz from the capture model property."""
        return capture.center_frequency_ghz

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_sample_rate_mhz(self, capture: Capture) -> float | None:
        """Sample rate in MHz from the model. None if not indexed in OpenSearch."""
        return capture.sample_rate_mhz

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_length_of_capture_ms(self, capture: Capture) -> int | None:
        """Capture length in milliseconds (OpenSearch bounds are seconds)."""
        if capture.end_time is None or capture.start_time is None:
            return None

        return (capture.end_time - capture.start_time) * 1000

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_file_cadence_ms(self, capture: Capture) -> int | None:
        """Get the file cadence in milliseconds. None if not indexed in OpenSearch."""
        return capture.file_cadence

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_capture_start_epoch_sec(self, capture: Capture) -> int | None:
        """Capture start as Unix epoch seconds. None if not in OpenSearch."""
        return capture.start_time

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_capture_start_iso_utc(self, capture: Capture) -> str | None:
        """Indexed capture start as ISO 8601 UTC (``Z``). None if unavailable."""
        if capture.start_time is None:
            return None

        return _epoch_sec_to_iso_utc_z(capture.start_time)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_capture_end_iso_utc(self, capture: Capture) -> str | None:
        """Indexed capture end as ISO 8601 UTC (``Z``). None if unavailable."""
        if capture.end_time is None:
            return None

        return _epoch_sec_to_iso_utc_z(capture.end_time)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_capture_start_display(self, capture: Capture) -> str | None:
        """Indexed capture start in the active timezone for display."""
        if capture.start_time is None:
            return None

        return _epoch_sec_to_local_display(capture.start_time)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_capture_end_display(self, capture: Capture) -> str | None:
        """Indexed capture end in the active timezone for display."""
        if capture.end_time is None:
            return None

        return _epoch_sec_to_local_display(capture.end_time)

    @extend_schema_field(serializers.DictField)
    def get_capture_props(self, capture: Capture) -> dict[str, Any]:
        """Retrieve the indexed metadata for the capture."""
        # check if this is a many=True serialization
        is_many = bool(
            self.parent and isinstance(self.parent, serializers.ListSerializer),
        )

        if not is_many or not self.parent:
            return retrieve_indexed_metadata(capture)

        # cache the metadata for all objects if not already done
        if not hasattr(self.parent, "capture_props_cache") and self.parent.instance:
            # convert QuerySet to list if needed
            instances: list[Capture] = cast(
                "list[Capture]",
                list(self.parent.instance)
                if self.parent is not None and hasattr(self.parent.instance, "__iter__")
                else [self.parent.instance if self.parent else capture],
            )
            self.parent.capture_props_cache = retrieve_indexed_metadata(instances)

        # return the cached metadata for this specific object
        return self.parent.capture_props_cache.get(str(capture.uuid), {})

    def get_formatted_created_at(self, capture: Capture) -> str:
        """Get the created_at date in the desired format."""
        return capture.created_at.strftime("%m/%d/%Y %I:%M:%S %p")

    def get_capture_type_display(self, capture: Capture) -> str:
        """Get the display value for the capture type."""
        return capture.get_capture_type_display()

    @extend_schema_field(DEPRECATEDPostProcessedDataSerializer(many=True))
    def get_post_processed_data(self, obj: Capture) -> Any:
        """Get all post-processed data for this capture."""
        processed_data = obj.visualization_post_processed_data.all().order_by(
            "processing_type", "-created_at"
        )
        return DEPRECATEDPostProcessedDataSerializer(processed_data, many=True).data

    class Meta:
        model = Capture
        fields = "__all__"


class CapturePostSerializer(serializers.ModelSerializer[Capture]):
    capture_props = serializers.SerializerMethodField()

    class Meta:
        model = Capture
        fields = [
            "uuid",
            "channel",
            "scan_group",
            "capture_type",
            "top_level_dir",
            "index_name",
            "name",
            "owner",
            "capture_props",
        ]
        read_only_fields = ["uuid"]
        required_fields_by_capture_type = {
            CaptureType.DigitalRF: [
                "capture_type",
                "top_level_dir",
                "index_name",
                "channel",
            ],
            CaptureType.RadioHound: [
                "capture_type",
                "top_level_dir",
                "index_name",
                "scan_group",
            ],
            CaptureType.SigMF: [
                "capture_type",
                "top_level_dir",
                "index_name",
            ],
        }

    @classmethod
    def get_required_fields(cls, capture_type: str) -> list[str]:
        """Get required fields for a capture type."""
        return cls.Meta.required_fields_by_capture_type[CaptureType(capture_type)]

    @extend_schema_field(serializers.DictField)
    def get_capture_props(self, capture: Capture) -> dict[str, Any]:
        """Retrieve the indexed metadata for the capture."""
        return retrieve_indexed_metadata(capture)

    def is_valid(self, *, raise_exception: bool = True) -> bool:
        """Checks if the data is valid."""
        initial_data = cast("dict[str, str]", self.initial_data)
        if not initial_data:
            self._errors = {"detail": ["No data provided."]}
            return super().is_valid(raise_exception=raise_exception)

        # check that the capture_type is valid
        capture_type: str = initial_data.get("capture_type", "")
        valid_types = [t.value for t in CaptureType]
        if capture_type not in valid_types:
            self._errors = {"capture_type": ["Invalid capture type."]}
            return super().is_valid(raise_exception=raise_exception)

        # check that the required fields are in the initial data
        for field in self.get_required_fields(capture_type):
            if field not in initial_data:
                self._errors = {field: ["This field is required."]}
                return super().is_valid(raise_exception=raise_exception)

        return super().is_valid(raise_exception=raise_exception)

    def create(self, validated_data: dict[str, Any]) -> Capture:
        # set the owner to the request user
        validated_data["owner"] = self.context["request_user"]
        try:
            validated_data["top_level_dir"] = normalize_top_level_dir(
                validated_data["top_level_dir"],
            )
        except ValueError as e:
            raise serializers.ValidationError({"top_level_dir": str(e)}) from e
        return super().create(validated_data=validated_data)

    def update(self, instance: Capture, validated_data: dict[str, Any]) -> Capture:
        try:
            validated_data["top_level_dir"] = normalize_top_level_dir(
                validated_data["top_level_dir"],
            )
        except ValueError as e:
            raise serializers.ValidationError({"top_level_dir": str(e)}) from e
        return super().update(instance=instance, validated_data=validated_data)


def normalize_top_level_dir(unknown_path: str) -> str:
    """Normalize the top level directory path."""
    # Validate input parameter
    if unknown_path is None:
        error_msg = "top_level_dir cannot be None"
        raise ValueError(error_msg)

    valid_path = str(unknown_path).strip()

    # Validate that path is not empty after stripping whitespace
    if not valid_path:
        error_msg = "top_level_dir cannot be empty or whitespace-only"
        raise ValueError(error_msg)

    # top level dir must start with '/'
    if not valid_path.startswith("/"):
        valid_path = "/" + valid_path

    # top level dir must not end with '/'
    return valid_path.rstrip("/")


class ChannelMetadataSerializer(serializers.Serializer):
    """Serializer for channel-specific metadata in composite captures."""

    channel = serializers.CharField()
    uuid = serializers.UUIDField()
    channel_metadata = serializers.DictField()


class CompositeChannelEntrySerializer(serializers.Serializer):
    """One channel in a composite capture, including per-channel index bounds."""

    channel = serializers.CharField()
    uuid = serializers.UUIDField()
    channel_metadata = serializers.DictField()
    capture_start_epoch_sec = serializers.IntegerField(allow_null=True, required=False)
    capture_end_epoch_sec = serializers.IntegerField(allow_null=True, required=False)
    capture_start_iso_utc = serializers.CharField(allow_null=True, required=False)
    capture_end_iso_utc = serializers.CharField(allow_null=True, required=False)
    capture_start_display = serializers.CharField(allow_null=True, required=False)
    capture_end_display = serializers.CharField(allow_null=True, required=False)
    length_of_capture_ms = serializers.IntegerField(allow_null=True, required=False)
    file_cadence_ms = serializers.IntegerField(allow_null=True, required=False)


class CompositeCaptureSerializer(serializers.Serializer):
    """Serializer for composite captures that contain multiple channels."""

    # Common fields from all captures
    uuid = serializers.UUIDField()
    capture_type = serializers.CharField()
    capture_type_display = serializers.CharField()
    top_level_dir = serializers.CharField()
    index_name = serializers.CharField()
    origin = serializers.CharField()
    is_multi_channel = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    deleted_at = serializers.DateTimeField(allow_null=True)
    is_deleted = serializers.BooleanField()
    is_public = serializers.BooleanField()
    is_shared = serializers.SerializerMethodField()
    owner = UserGetSerializer()

    # Channel-specific fields (enriched with OpenSearch bounds per channel)
    channels = serializers.SerializerMethodField()

    # Computed fields
    share_permissions = serializers.SerializerMethodField()
    files = serializers.SerializerMethodField()
    total_file_count = serializers.SerializerMethodField()
    total_file_size = serializers.SerializerMethodField()
    data_files_info = serializers.SerializerMethodField()
    formatted_created_at = serializers.SerializerMethodField()
    length_of_capture_ms = serializers.SerializerMethodField()
    file_cadence_ms = serializers.SerializerMethodField()
    capture_start_epoch_sec = serializers.SerializerMethodField()
    capture_start_iso_utc = serializers.SerializerMethodField()
    capture_end_iso_utc = serializers.SerializerMethodField()
    capture_start_display = serializers.SerializerMethodField()
    capture_end_display = serializers.SerializerMethodField()

    def _captures_bulk_by_uuid(self, obj: dict[str, Any]) -> dict[str, Capture]:
        """One DB query per composite when ``include_serializer_aux`` was False."""
        key = str(obj.get("uuid", ""))
        if not hasattr(self, "_captures_bulk_cache"):
            self._captures_bulk_cache: dict[str, dict[str, Capture]] = {}
        if key not in self._captures_bulk_cache:
            uuids = [ch["uuid"] for ch in obj.get("channels") or []]
            self._captures_bulk_cache[key] = (
                {str(c.uuid): c for c in Capture.objects.filter(uuid__in=uuids)}
                if uuids
                else {}
            )
        return self._captures_bulk_cache[key]

    def _capture_for_channel(
        self, obj: dict[str, Any], channel_entry: dict[str, Any]
    ) -> Capture | None:
        """Resolve Capture; prefer auxiliary map from build, otherwise bulk queryset."""
        by_uuid = obj.get("_captures_by_uuid")
        uuid_key = str(channel_entry["uuid"])
        if isinstance(by_uuid, dict):
            hit = cast("Capture | None", by_uuid.get(uuid_key))
            if hit is not None:
                return hit
        hit = self._captures_bulk_by_uuid(obj).get(uuid_key)
        if hit is not None:
            return hit
        try:
            return Capture.objects.get(uuid=channel_entry["uuid"])
        except Capture.DoesNotExist:
            return None

    def _enriched_channels(self, obj: dict[str, Any]) -> list[dict[str, Any]]:
        """Per-channel rows with OpenSearch bounds (each channel may differ)."""
        key = str(obj.get("uuid", ""))
        if not hasattr(self, "_enriched_channels_cache"):
            self._enriched_channels_cache: dict[str, list[dict[str, Any]]] = {}
        if key not in self._enriched_channels_cache:
            out: list[dict[str, Any]] = []
            for ch in obj.get("channels") or []:
                entry: dict[str, Any] = {
                    "channel": ch["channel"],
                    "uuid": ch["uuid"],
                    "channel_metadata": ch.get("channel_metadata", {}),
                }
                pre_meta = cast(
                    "dict[str, Any] | None",
                    ch.get("_per_channel_os_meta"),
                )
                if pre_meta is not None:
                    entry.update(_channel_row_bounds_from_os_meta(pre_meta))
                    out.append(entry)
                    continue
                capture = self._capture_for_channel(obj, ch)
                if capture is None:
                    entry.update(
                        {
                            "capture_start_epoch_sec": None,
                            "capture_end_epoch_sec": None,
                            "capture_start_iso_utc": None,
                            "capture_end_iso_utc": None,
                            "capture_start_display": None,
                            "capture_end_display": None,
                            "length_of_capture_ms": None,
                            "file_cadence_ms": None,
                        }
                    )
                else:
                    # One OS round-trip per Capture instance via instance cache.
                    meta = capture.get_opensearch_metadata()
                    entry.update(_channel_row_bounds_from_os_meta(meta))
                out.append(entry)
            self._enriched_channels_cache[key] = out
        return self._enriched_channels_cache[key]

    def _composite_envelope_bounds(
        self,
        obj: dict[str, Any],
    ) -> tuple[int, int] | None:
        """Earliest channel start and latest channel end (seconds)."""
        pairs = [
            (row["capture_start_epoch_sec"], row["capture_end_epoch_sec"])
            for row in self._enriched_channels(obj)
            if row.get("capture_start_epoch_sec") is not None
            and row.get("capture_end_epoch_sec") is not None
        ]
        if not pairs:
            return None
        return min(s for s, _ in pairs), max(e for _, e in pairs)

    @extend_schema_field(CompositeChannelEntrySerializer(many=True))
    def get_channels(self, obj: dict[str, Any]) -> list[dict[str, Any]]:
        return self._enriched_channels(obj)

    def get_share_permissions(self, obj: dict[str, Any]) -> list[UserSharePermission]:
        """Get the share permissions for the composite capture."""
        capture_uuid = obj.get("uuid")
        if capture_uuid is None:
            return []
        user_share_permissions = UserSharePermission.objects.filter(
            item_uuid=capture_uuid,
            item_type=ItemType.CAPTURE,
            is_deleted=False,
            is_enabled=True,
        )
        return UserSharePermissionSerializer(user_share_permissions, many=True).data

    def get_is_shared(self, obj: dict[str, Any]) -> bool:
        """Get whether the composite capture is shared.

        Returns:
            True if the composite capture has enabled share permissions,
            False otherwise.
        """
        capture_uuid = obj.get("uuid")
        if capture_uuid is None:
            return False
        return check_if_shared(capture_uuid, ItemType.CAPTURE)

    def get_files(self, obj: dict[str, Any]) -> ReturnList[File]:
        """Get all files from all channels in the composite capture."""
        all_files: list[File] = []

        exclude_files = (self.context or {}).get("exclude_files", False)
        if exclude_files:
            return all_files

        for channel_data in obj.get("channels") or []:
            capture = self._capture_for_channel(obj, channel_data)
            if capture is None:
                continue
            non_deleted_files = get_capture_files(capture, include_deleted=False)
            serializer = FileSummarySerializer(
                non_deleted_files,
                many=True,
                context=self.context or {},
            )
            all_files.extend(serializer.data)
        return cast("ReturnList[File]", all_files)

    @extend_schema_field(serializers.IntegerField())
    def get_total_file_count(self, obj: dict[str, Any]) -> int:
        """Total file count across all channels."""
        total = 0
        for channel_data in obj.get("channels") or []:
            capture = self._capture_for_channel(obj, channel_data)
            if capture is None:
                continue
            total += capture.get_files_summary()["total_count"]
        return total

    @extend_schema_field(serializers.IntegerField())
    def get_total_file_size(self, obj: dict[str, Any]) -> int:
        """Total file size across all channels."""
        total_size = 0
        for channel_data in obj.get("channels") or []:
            capture = self._capture_for_channel(obj, channel_data)
            if capture is None:
                continue
            total_size += capture.get_files_summary()["total_size"]
        return total_size

    def get_data_files_info(self, obj: dict[str, Any]) -> dict[str, Any]:
        """File summary aggregated across composite channels."""
        total_count = 0
        total_size = 0
        drf_count = 0
        drf_size = 0
        for channel_data in obj.get("channels") or []:
            capture = self._capture_for_channel(obj, channel_data)
            if capture is None:
                continue
            summary = capture.get_files_summary()
            total_count += summary["total_count"]
            total_size += summary["total_size"]
            data_files = summary.get("data_files")
            if data_files:
                drf_count += data_files["count"]
                drf_size += data_files["total_size"]

        result: dict[str, Any] = {
            "count": drf_count or total_count,
            "total_size": total_size,
            "total_count": total_count,
        }
        if drf_count:
            result["per_data_file_size"] = (
                float(drf_size) / drf_count if drf_count else None
            )
        return result

    @extend_schema_field(serializers.CharField)
    def get_formatted_created_at(self, obj: dict[str, Any]) -> str:
        """Format the created_at timestamp for display."""
        created_at = obj.get("created_at")
        if created_at:
            return created_at.strftime("%m/%d/%Y %I:%M:%S %p")
        return ""

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_length_of_capture_ms(self, obj: dict[str, Any]) -> int | None:
        """Span from earliest channel start to latest channel end (milliseconds)."""
        bounds = self._composite_envelope_bounds(obj)
        if bounds is None:
            return None
        start_time, end_time = bounds
        return (end_time - start_time) * 1000

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_file_cadence_ms(self, obj: dict[str, Any]) -> int | None:
        """Mean file cadence across channels (each channel may differ)."""
        cadences = [
            row["file_cadence_ms"]
            for row in self._enriched_channels(obj)
            if row.get("file_cadence_ms") is not None
        ]
        if not cadences:
            return None
        return round(sum(cadences) / len(cadences))

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_capture_start_epoch_sec(self, obj: dict[str, Any]) -> int | None:
        """Earliest indexed start among channels (epoch seconds)."""
        bounds = self._composite_envelope_bounds(obj)
        if bounds is None:
            return None
        start_time, _ = bounds
        return start_time

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_capture_start_iso_utc(self, obj: dict[str, Any]) -> str | None:
        bounds = self._composite_envelope_bounds(obj)
        if bounds is None:
            return None
        start_sec, _ = bounds
        return _epoch_sec_to_iso_utc_z(start_sec)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_capture_end_iso_utc(self, obj: dict[str, Any]) -> str | None:
        bounds = self._composite_envelope_bounds(obj)
        if bounds is None:
            return None
        _, end_sec = bounds
        return _epoch_sec_to_iso_utc_z(end_sec)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_capture_start_display(self, obj: dict[str, Any]) -> str | None:
        bounds = self._composite_envelope_bounds(obj)
        if bounds is None:
            return None
        start_sec, _ = bounds
        return _epoch_sec_to_local_display(start_sec)

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_capture_end_display(self, obj: dict[str, Any]) -> str | None:
        bounds = self._composite_envelope_bounds(obj)
        if bounds is None:
            return None
        _, end_sec = bounds
        return _epoch_sec_to_local_display(end_sec)


def build_composite_capture_data(
    captures: list[Capture],
    *,
    include_serializer_aux: bool = False,
) -> dict[str, Any]:
    """Build composite capture data from a list of captures with the same top_level_dir.

    Args:
        captures: List of Capture objects to combine into composite
        include_serializer_aux: When True, attach non-public fields used only by
            :class:`CompositeCaptureSerializer`: per-channel cached OpenSearch
            metadata (one search per capture) and a Capture map to avoid duplicate
            ORM lookups. Keep False for raw API payloads (capture list/search,
            nested dataset captures).

    Returns:
        dict: Composite capture data structure

    Raises:
        ValueError: If no captures are provided
    """
    if not captures:
        error_msg = "No captures provided for composite"
        raise ValueError(error_msg)

    # Use the first capture as the base for common fields
    base_capture = captures[0]

    # Build channel data with metadata
    captures_by_uuid: dict[str, Capture] | None = {} if include_serializer_aux else None
    channels: list[dict[str, Any]] = []
    for capture in captures:
        if captures_by_uuid is not None:
            captures_by_uuid[str(capture.uuid)] = capture
        channel_data: dict[str, Any] = {
            "channel": capture.channel,
            "uuid": capture.uuid,
            "channel_metadata": retrieve_indexed_metadata(capture),
        }
        if include_serializer_aux:
            channel_data["_per_channel_os_meta"] = capture.get_opensearch_metadata()
        channels.append(channel_data)

    # Serialize the owner field
    owner_serializer = UserGetSerializer(base_capture.owner)

    # Build composite data
    composite: dict[str, Any] = {
        "uuid": base_capture.uuid,  # Use first capture's UUID as composite UUID
        "capture_type": base_capture.capture_type,
        "capture_type_display": base_capture.get_capture_type_display(),
        "top_level_dir": base_capture.top_level_dir,
        "index_name": base_capture.index_name,
        "origin": base_capture.origin,
        "is_multi_channel": True,
        "created_at": base_capture.created_at,
        "updated_at": base_capture.updated_at,
        "deleted_at": base_capture.deleted_at,
        "is_deleted": base_capture.is_deleted,
        "is_public": base_capture.is_public,
        "owner": owner_serializer.data,
        "channels": channels,
    }
    if captures_by_uuid is not None:
        composite["_captures_by_uuid"] = captures_by_uuid
    return composite


def serialize_capture_or_composite(
    capture: Capture, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Serialize a capture as single or composite based on multi-channel status.

    Args:
        capture: Capture object to serialize
        context: Optional context for serialization

    Returns:
        dict: Serialized capture data
    """
    capture_data = capture.get_capture()

    if capture_data["is_composite"]:
        # Serialize as composite
        captures = capture_data["captures"]  # fresh DB instances (no cache yet)
        # Populate cache from bulk-loaded metadata to avoid individual
        # OpenSearch round-trips for each related capture.
        bulk_meta: dict[str, Any] | None = (context or {}).get("bulk_metadata")
        if bulk_meta is not None:
            Capture.set_bulk_metadata_cache(captures, bulk_meta)
            log.debug(
                "set_bulk_metadata_cache applied to %d related captures "
                "via serialize_capture_or_composite (multi-channel)",
                len(captures),
            )
        composite_data = build_composite_capture_data(
            captures,
            include_serializer_aux=True,
        )
        serializer = CompositeCaptureSerializer(composite_data, context=context)
        return serializer.data
    # Serialize as single capture
    serializer = CaptureGetSerializer(capture_data["capture"], context=context)
    return serializer.data


class CaptureFederationSerializer(serializers.ModelSerializer[Capture]):
    """Public-safe capture payload for federation export (sync / OpenSearch)."""

    site_name = serializers.SerializerMethodField()
    file_count = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()
    capture_props = serializers.SerializerMethodField()
    public_dataset_ids = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(
        format="%Y-%m-%d %H:%M:%S%z",
        read_only=True,
    )
    updated_at = serializers.DateTimeField(
        format="%Y-%m-%d %H:%M:%S%z",
        read_only=True,
    )
    deleted_at = serializers.DateTimeField(
        format="%Y-%m-%d %H:%M:%S%z",
        read_only=True,
    )

    class Meta:
        model = Capture
        fields = [
            "uuid",
            "name",
            "capture_type",
            "channel",
            "scan_group",
            "top_level_dir",
            "site_name",
            "file_count",
            "size",
            "capture_props",
            "public_dataset_ids",
            "created_at",
            "updated_at",
            "is_deleted",
            "deleted_at",
        ]

    def get_site_name(self, obj: Capture) -> str:
        return str((self.context or {})["site_name"])

    def get_file_count(self, obj: Capture) -> int:
        return int(obj.get_files_summary()["total_count"])

    def get_size(self, obj: Capture) -> int:
        return int(obj.get_files_summary()["total_size"])

    def get_capture_props(self, obj: Capture) -> dict[str, Any]:
        return obj.get_opensearch_metadata() or {}

    def get_public_dataset_ids(self, obj: Capture) -> list[str]:
        qs = obj.datasets.federation_exportable()
        return [str(dataset.uuid) for dataset in qs]
