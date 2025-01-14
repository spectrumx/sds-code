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

        if is_many and self.parent and self.parent.instance:
            # Cache the metadata for all objects if not already done
            if not hasattr(self.parent, "metadata_cache"):
                self.parent.metadata_cache = retrieve_indexed_metadata(
                    self.parent.instance,
                    is_many=True,
                )
            # Return the cached metadata for this specific object
            return self.parent.metadata_cache.get(str(obj.uuid), {})

        # Single object serialization - use existing logic
        return retrieve_indexed_metadata(obj, is_many=False)

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
