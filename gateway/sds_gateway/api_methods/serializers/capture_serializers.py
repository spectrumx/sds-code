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
        return retrieve_indexed_metadata(obj)

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
