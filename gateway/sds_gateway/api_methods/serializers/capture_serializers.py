from rest_framework import serializers

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.serializers.file_serializers import UserSerializer


class CaptureGetSerializer(serializers.ModelSerializer):
    owner = UserSerializer()

    class Meta:
        model = Capture
        fields = "__all__"


class CapturePostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Capture
        fields = ["uuid", "channel", "capture_type", "index_name", "owner"]
        read_only_fields = ["uuid"]
