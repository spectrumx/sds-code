"""Capture serializers for the SDS Gateway API methods."""

from typing import Any
from typing import cast

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from sds_gateway.api_methods.helpers.index_handling import retrieve_indexed_metadata
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.serializers.user_serializer import UserGetSerializer


class CaptureGetSerializer(serializers.ModelSerializer):
    owner = UserGetSerializer()
    capture_props = serializers.SerializerMethodField()

    @extend_schema_field(serializers.DictField)
    def get_capture_props(self, obj):
        # Check if this is a many=True serialization
        is_many = bool(
            self.parent and isinstance(self.parent, serializers.ListSerializer),
        )

        if not is_many or not self.parent:
            return retrieve_indexed_metadata(obj, is_many=False)

        # Cache the metadata for all objects if not already done
        if not hasattr(self.parent, "capture_props_cache"):
            # Convert QuerySet to list if needed
            instances = (
                list(self.parent.instance)
                if self.parent and hasattr(self.parent.instance, "__iter__")
                else [self.parent.instance if self.parent else obj]
            )
            self.parent.capture_props_cache = retrieve_indexed_metadata(
                instances,
                is_many=True,
            )

        # Return the cached metadata for this specific object
        return self.parent.capture_props_cache.get(str(obj.uuid), {})

    class Meta:
        model = Capture
        fields = "__all__"


class CapturePostSerializer(serializers.ModelSerializer):
    capture_props = serializers.SerializerMethodField()

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
        initial_data = cast(dict[str, str], self.initial_data)
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
        # Set the owner to the request user
        validated_data["owner"] = self.context["request_user"]
        return super().create(validated_data)
