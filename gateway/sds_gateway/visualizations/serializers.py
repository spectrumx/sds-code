"""Serializers for the visualizations app."""

from rest_framework import serializers

from .models import PostProcessedData


class PostProcessedDataSerializer(serializers.ModelSerializer):
    """Serializer for PostProcessedData model."""

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
            "processing_error",
            "processed_at",
            "pipeline_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "uuid",
            "created_at",
            "updated_at",
            "pipeline_id",
        ]
