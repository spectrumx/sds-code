"""Dataset serializers for the API methods."""

from rest_framework import serializers

from sds_gateway.api_methods.models import Dataset


class DatasetGetSerializer(serializers.ModelSerializer[Dataset]):
    class Meta:
        model = Dataset
        fields = "__all__"
