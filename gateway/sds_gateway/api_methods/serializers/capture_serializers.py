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
    files = serializers.SerializerMethodField()
    center_frequency_ghz = serializers.SerializerMethodField()
    sample_rate_mhz = serializers.SerializerMethodField()
    files_count = serializers.SerializerMethodField()
    total_file_size = serializers.SerializerMethodField()
    formatted_created_at = serializers.SerializerMethodField()

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
        return capture.created_at.strftime("%m/%d/%Y %I:%M:%S")

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
        validated_data["top_level_dir"] = normalize_top_level_dir(
            validated_data["top_level_dir"],
        )
        return super().create(validated_data=validated_data)

    def update(self, instance: Capture, validated_data: dict[str, Any]) -> Capture:
        validated_data["top_level_dir"] = normalize_top_level_dir(
            validated_data["top_level_dir"],
        )
        return super().update(instance=instance, validated_data=validated_data)


def normalize_top_level_dir(unknown_path: str) -> str:
    """Normalize the top level directory path."""
    valid_path = str(unknown_path)

    # top level dir must start with '/'
    if not valid_path.startswith("/"):
        valid_path = "/" + valid_path

    # top level dir must not end with '/'
    return valid_path.rstrip("/")
