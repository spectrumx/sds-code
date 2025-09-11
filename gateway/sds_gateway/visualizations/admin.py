"""Admin configuration for the visualizations app."""

from django.contrib import admin

from .models import PostProcessedData


@admin.register(PostProcessedData)
class PostProcessedDataAdmin(admin.ModelAdmin):
    """Admin interface for PostProcessedData model."""

    list_display = (
        "processing_type",
        "capture",
        "processing_status",
        "processed_at",
        "pipeline_id",
        "created_at",
    )
    list_filter = (
        "processing_type",
        "processing_status",
        "processed_at",
        "created_at",
        "capture__capture_type",
    )
    search_fields = (
        "uuid",
        "processing_type",
        "capture__name",
        "capture__uuid",
        "pipeline_id",
        "processing_error",
    )
    readonly_fields = (
        "uuid",
        "created_at",
        "updated_at",
        "processed_at",
    )
    ordering = ("-created_at",)

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "uuid",
                    "capture",
                    "processing_type",
                    "processing_status",
                )
            },
        ),
        (
            "Processing Details",
            {
                "fields": (
                    "processing_parameters",
                    "pipeline_id",
                    "processed_at",
                    "processing_error",
                )
            },
        ),
        (
            "Data & Metadata",
            {
                "fields": (
                    "data_file",
                    "metadata",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        """Optimize queryset with related fields."""
        return super().get_queryset(request).select_related("capture")
