"""Capture serializers for the SDS Gateway API methods."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from sds_gateway.api_methods.helpers.index_handling import retrieve_indexed_metadata
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.serializers.user_serializer import UserGetSerializer


class CaptureGetSerializer(serializers.ModelSerializer[Capture]):
    owner = UserGetSerializer()
    metadata = serializers.SerializerMethodField()

    @extend_schema_field(serializers.DictField)
    def get_metadata(self, obj):
        # Check if this is a many=True serialization
        is_many = bool(
            self.parent and isinstance(self.parent, serializers.ListSerializer),
        )

        if not is_many or not self.parent:
            return retrieve_indexed_metadata(obj, is_many=False)

        # Cache the metadata for all objects if not already done
        if not hasattr(self.parent, "metadata_cache"):
            # Convert QuerySet to list if needed
            instances = (
                list(self.parent.instance)
                if self.parent and hasattr(self.parent.instance, "__iter__")
                else [self.parent.instance if self.parent else obj]
            )
            self.parent.metadata_cache = retrieve_indexed_metadata(
                instances,
                is_many=True,
            )

        # Return the cached metadata for this specific object
        return self.parent.metadata_cache.get(str(obj.uuid), {})

    class Meta:
        model = Capture
        fields = "__all__"


class CapturePostSerializer(serializers.ModelSerializer[Capture]):
    class Meta:
        model = Capture
        fields = [
            "uuid",
            "channel",
            "capture_type",
            "top_level_dir",
            "index_name",
            "owner",
        ]
        read_only_fields = ["uuid"]
