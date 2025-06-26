"""Capture serializers for the SDS Gateway API methods."""

from typing import Any
from typing import cast

from django.db.models import Sum
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnList

from sds_gateway.api_methods.helpers.index_handling import retrieve_indexed_metadata
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.serializers.user_serializer import UserGetSerializer


class FileCaptureListSerializer(serializers.ModelSerializer[File]):
    class Meta:
        model = File
        fields = [
            "uuid",
            "name",
            "directory",
        ]


class CaptureGetSerializer(serializers.ModelSerializer[Capture]):
    owner = UserGetSerializer()
    capture_props = serializers.SerializerMethodField()
    channels_metadata = serializers.SerializerMethodField()
    files = serializers.SerializerMethodField()
    center_frequency_ghz = serializers.SerializerMethodField()
    sample_rate_mhz = serializers.SerializerMethodField()
    files_count = serializers.SerializerMethodField()
    total_file_size = serializers.SerializerMethodField()
    channels = serializers.SerializerMethodField()
    primary_channel = serializers.SerializerMethodField()

    def get_files(self, capture: Capture) -> ReturnList[File]:
        """Get the files for the capture.

        Returns:
            A list of serialized file objects with uuid, name, and directory fields.
        """
        non_deleted_files = File.objects.filter(
            capture=capture,
            is_deleted=False,
        )
        serializer = FileCaptureListSerializer(
            non_deleted_files,
            many=True,
            context=self.context,
        )
        return cast("ReturnList[File]", serializer.data)

    @extend_schema_field(serializers.FloatField)
    def get_center_frequency_ghz(self, capture: Capture) -> float | None:
        """Get the center frequency in GHz from the capture model property."""
        return capture.center_frequency_ghz

    @extend_schema_field(serializers.FloatField)
    def get_sample_rate_mhz(self, capture: Capture) -> float | None:
        """Get the sample rate in MHz from the capture model property."""
        return capture.sample_rate_mhz

    @extend_schema_field(serializers.IntegerField)
    def get_files_count(self, capture: Capture) -> int:
        """Get the count of files associated with this capture."""
        return capture.files.filter(is_deleted=False).count()

    @extend_schema_field(serializers.IntegerField)
    def get_total_file_size(self, capture: Capture) -> int:
        """Get the total file size of all files associated with this capture."""
        result = capture.files.filter(is_deleted=False).aggregate(
            total_size=Sum("size")
        )
        return result["total_size"] or 0

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_channels(self, capture: Capture) -> list[str]:
        """Get the list of channel names for this capture."""
        return capture.channels

    @extend_schema_field(serializers.CharField())
    def get_primary_channel(self, capture: Capture) -> str | None:
        """Get the primary channel name for backward compatibility."""
        return capture.primary_channel

    @extend_schema_field(serializers.DictField)
    def get_capture_props(self, capture: Capture) -> dict[str, Any]:
        """Retrieve the indexed metadata for the capture (backward compatibility)."""
        # check if this is a many=True serialization
        is_many = bool(
            self.parent and isinstance(self.parent, serializers.ListSerializer),
        )

        if not is_many or not self.parent:
            metadata = retrieve_indexed_metadata(capture)
            # For DRF captures, return the first channel's props for backward
            # compatibility
            if (
                capture.capture_type == CaptureType.DigitalRF
                and isinstance(metadata, list)
                and metadata
            ):
                return metadata[0].get("channel_props", {})
            return metadata

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
        metadata = self.parent.capture_props_cache.get(str(capture.uuid), {})
        # For DRF captures, return the first channel's props for backward
        # compatibility
        if (
            capture.capture_type == CaptureType.DigitalRF
            and isinstance(metadata, list)
            and metadata
        ):
            return metadata[0].get("channel_props", {})
        return metadata

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_channels_metadata(self, capture: Capture) -> list[dict[str, Any]]:
        """Retrieve the channels metadata for DRF captures."""
        # check if this is a many=True serialization
        is_many = bool(
            self.parent and isinstance(self.parent, serializers.ListSerializer),
        )

        if not is_many or not self.parent:
            metadata = retrieve_indexed_metadata(capture)
            # For DRF captures, return the channels structure
            if capture.capture_type == CaptureType.DigitalRF:
                return metadata if isinstance(metadata, list) else []
            return []

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
        metadata = self.parent.capture_props_cache.get(str(capture.uuid), {})
        # For DRF captures, return the channels structure
        if capture.capture_type == CaptureType.DigitalRF:
            return metadata if isinstance(metadata, list) else []
        return []

    class Meta:
        model = Capture
        fields = "__all__"


class CapturePostSerializer(serializers.ModelSerializer[Capture]):
    capture_props = serializers.SerializerMethodField()
    channels_metadata = serializers.SerializerMethodField()
    channels = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        help_text="List of channel names for DigitalRF captures",
    )

    class Meta:
        model = Capture
        fields = [
            "uuid",
            "channels",
            "scan_group",
            "capture_type",
            "top_level_dir",
            "index_name",
            "owner",
            "capture_props",
            "channels_metadata",
        ]
        read_only_fields = ["uuid"]
        required_fields_by_capture_type = {
            CaptureType.DigitalRF: [
                "capture_type",
                "top_level_dir",
                "index_name",
                "channels",
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
        """Retrieve the indexed metadata for the capture (backward compatibility)."""
        metadata = retrieve_indexed_metadata(capture)
        # For DRF captures, return the first channel's props for backward
        # compatibility
        if (
            capture.capture_type == CaptureType.DigitalRF
            and isinstance(metadata, list)
            and metadata
        ):
            return metadata[0].get("channel_props", {})
        return metadata

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_channels_metadata(self, capture: Capture) -> list[dict[str, Any]]:
        """Retrieve the channels metadata for DRF captures."""
        metadata = retrieve_indexed_metadata(capture)
        # For DRF captures, return the channels structure
        if capture.capture_type == CaptureType.DigitalRF:
            return metadata if isinstance(metadata, list) else []
        return []

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
        validated_data["top_level_dir"] = normalize_top_level_dir(
            validated_data["top_level_dir"],
        )

        # Handle channels field
        if "channels" in validated_data:
            capture = super().create(validated_data=validated_data)
            capture.channels = validated_data["channels"]
            capture.save()
            return capture

        return super().create(validated_data=validated_data)

    def update(self, instance: Capture, validated_data: dict[str, Any]) -> Capture:
        validated_data["top_level_dir"] = normalize_top_level_dir(
            validated_data["top_level_dir"],
        )

        # Handle channels field
        if "channels" in validated_data:
            instance.channels = validated_data["channels"]

        return super().update(instance=instance, validated_data=validated_data)


def normalize_top_level_dir(unknown_path: str) -> str:
    """Normalize the top level directory path."""
    valid_path = str(unknown_path)

    # top level dir must start with '/'
    if not valid_path.startswith("/"):
        valid_path = "/" + valid_path

    # top level dir must not end with '/'
    return valid_path.rstrip("/")
