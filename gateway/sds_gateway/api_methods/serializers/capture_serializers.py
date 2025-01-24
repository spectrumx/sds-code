"""Capture serializers for the SDS Gateway API methods."""

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from sds_gateway.api_methods.helpers.index_handling import retrieve_indexed_metadata
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.serializers.user_serializer import UserGetSerializer


class CaptureGetSerializer(serializers.ModelSerializer[Capture]):
    owner = UserGetSerializer()
    capture_props = serializers.SerializerMethodField()

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
        if not hasattr(self.parent, "capture_props_cache"):
            # Convert QuerySet to list if needed
            instances: list[Capture] = (
                list(self.parent.instance)
                if self.parent is not None and hasattr(self.parent.instance, "__iter__")
                else [self.parent.instance if self.parent else capture]
            )
            self.parent.capture_props_cache = retrieve_indexed_metadata(
                instances,
            )

        # return the cached metadata for this specific object
        return self.parent.capture_props_cache.get(str(capture.uuid), {})

    class Meta:
        model = Capture
        fields = "__all__"


class CapturePostSerializer(serializers.ModelSerializer[Capture]):
    capture_props = serializers.SerializerMethodField()

    @extend_schema_field(serializers.DictField)
    def get_capture_props(self, capture: Capture) -> dict[str, Any]:
        """Retrieve the indexed metadata for the capture."""
        return retrieve_indexed_metadata(capture)

    def create(self, validated_data: dict[str, Any]) -> Capture:
        # Set the owner to the request user
        validated_data["owner"] = self.context["request_user"]
        return super().create(validated_data)

    def is_valid(self, *, raise_exception: bool = True) -> bool:
        """Check if the serializer is valid."""
        if not self.initial_data:
            self._errors = {"detail": ["No data provided."]}
        return super().is_valid(raise_exception=raise_exception)

    class Meta:
        model = Capture
        fields = [
            "uuid",
            "channel",
            "capture_type",
            "top_level_dir",
            "index_name",
            "owner",
            "capture_props",
        ]
        read_only_fields = ["uuid"]
