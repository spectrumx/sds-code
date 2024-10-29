from rest_framework import serializers

from sds_gateway.api_methods.models import Capture


class CaptureGetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Capture
        fields = "__all__"


class CapturePostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Capture
        fields = ["uuid", "channel", "capture_type", "index_name"]
        read_only_fields = ["uuid"]
