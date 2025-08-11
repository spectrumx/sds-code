"""Dataset serializers for the API methods."""

from rest_framework import serializers

from sds_gateway.api_methods.models import Dataset


class DatasetGetSerializer(serializers.ModelSerializer[Dataset]):
    authors = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(format="%m/%d/%Y %H:%M:%S", read_only=True)
    is_shared_with_me = serializers.BooleanField(read_only=True, default=False)
    is_owner = serializers.BooleanField(read_only=True, default=False)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    def get_authors(self, obj):
        return obj.authors[0] if obj.authors else None

    class Meta:
        model = Dataset
        fields = "__all__"
