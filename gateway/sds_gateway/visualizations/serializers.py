"""Serializers for the visualizations app."""

from rest_framework import serializers

from .models import PostProcessedData


class PostProcessedDataSerializer(serializers.ModelSerializer):
    """Serializer for PostProcessedData model."""

    error_info = serializers.SerializerMethodField()
    has_source_data_error = serializers.SerializerMethodField()

    class Meta:
        model = PostProcessedData
        fields = [
            "uuid",
            "capture",
            "processing_type",
            "processing_parameters",
            "data_file",
            "metadata",
            "processing_status",
            "processed_at",
            "pipeline_id",
            "created_at",
            "updated_at",
            "error_info",
            "has_source_data_error",
        ]
        read_only_fields = [
            "uuid",
            "created_at",
            "updated_at",
            "pipeline_id",
            "error_info",
            "has_source_data_error",
        ]

    def get_error_info(self, obj):
        return obj.get_error_info()

    def get_has_source_data_error(self, obj):
        return obj.has_source_data_error()
