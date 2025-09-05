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
from sds_gateway.api_methods.models import DEPRECATEDPostProcessedData
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
    capture_props = serializers.SerializerMethodField()
    files = serializers.SerializerMethodField()
    center_frequency_ghz = serializers.SerializerMethodField()
    sample_rate_mhz = serializers.SerializerMethodField()
    files_count = serializers.SerializerMethodField()
    total_file_size = serializers.SerializerMethodField()
    formatted_created_at = serializers.SerializerMethodField()
    capture_type_display = serializers.SerializerMethodField()
    post_processed_data = serializers.SerializerMethodField()

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
    owner = UserGetSerializer()

    # Channel-specific fields
    channels = serializers.ListField(child=ChannelMetadataSerializer())

    # Computed fields
    files = serializers.SerializerMethodField()
    files_count = serializers.SerializerMethodField()
    total_file_size = serializers.SerializerMethodField()
    formatted_created_at = serializers.SerializerMethodField()

    def get_files(self, obj: dict[str, Any]) -> ReturnList[File]:
        """Get all files from all channels in the composite capture."""
        all_files = []
        for channel_data in obj["channels"]:
            capture_uuid = channel_data["uuid"]
            capture = Capture.objects.get(uuid=capture_uuid)
            non_deleted_files = File.objects.filter(
                capture=capture,
                is_deleted=False,
            )
            serializer = FileCaptureListSerializer(
                non_deleted_files,
                many=True,
                context=self.context,
            )
            all_files.extend(serializer.data)
        return cast("ReturnList[File]", all_files)

    @extend_schema_field(serializers.IntegerField)
    def get_files_count(self, obj: dict[str, Any]) -> int:
        """Get the total count of files across all channels."""
        total_count = 0
        for channel_data in obj["channels"]:
            capture_uuid = channel_data["uuid"]
            capture = Capture.objects.get(uuid=capture_uuid)
            total_count += capture.files.filter(is_deleted=False).count()
        return total_count

    @extend_schema_field(serializers.IntegerField)
    def get_total_file_size(self, obj: dict[str, Any]) -> int:
        """Get the total file size across all channels."""
        total_size = 0
        for channel_data in obj["channels"]:
            capture_uuid = channel_data["uuid"]
            capture = Capture.objects.get(uuid=capture_uuid)
            result = capture.files.filter(is_deleted=False).aggregate(
                total_size=Sum("size")
            )
            total_size += result["total_size"] or 0
        return total_size

    @extend_schema_field(serializers.CharField)
    def get_formatted_created_at(self, obj: dict[str, Any]) -> str:
        """Format the created_at timestamp for display."""
        created_at = obj.get("created_at")
        if created_at:
            return created_at.strftime("%m/%d/%Y %I:%M:%S %p")
        return ""


def build_composite_capture_data(captures: list[Capture]) -> dict[str, Any]:
    """Build composite capture data from a list of captures with the same top_level_dir.

    Args:
        captures: List of Capture objects to combine into composite

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
    channels = []
    for capture in captures:
        channel_data = {
            "channel": capture.channel,
            "uuid": capture.uuid,
            "channel_metadata": retrieve_indexed_metadata(capture),
        }
        channels.append(channel_data)

    # Serialize the owner field
    owner_serializer = UserGetSerializer(base_capture.owner)

    # Build composite data
    return {
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
        composite_data = build_composite_capture_data(capture_data["captures"])
        serializer = CompositeCaptureSerializer(composite_data, context=context)
        return serializer.data
    # Serialize as single capture
    serializer = CaptureGetSerializer(capture_data["capture"], context=context)
    return serializer.data
