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
            "error",
        ]

    def get_error(self, obj):
        if obj.cog_error:
            return {
                "error_type": obj.cog_error.error_type,
                "traceback": obj.cog_error.traceback,
                "timestamp": obj.cog_error.timestamp,
                "task_run_id": obj.cog_error.task_run.id,
            }
        return obj.processing_error
