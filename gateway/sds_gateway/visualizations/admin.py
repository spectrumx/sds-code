"""Admin configuration for the visualizations app."""

from django.contrib import admin

from .models import PostProcessedData


@admin.register(PostProcessedData)
class PostProcessedDataAdmin(admin.ModelAdmin):
    """Admin interface for PostProcessedData model."""

    list_display = (
        "processing_type",
        "capture",
        "get_owner",
        "processing_status",
        "pipeline_id",
        "processed_at",
        "has_error",
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
                    "cog_error",
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

    @admin.display(description="Owner")
    def get_owner(self, obj):
        """Get owner through the capture FK."""
        if obj.capture and obj.capture.owner:
            return obj.capture.owner.email
        return "-"

    @admin.display(boolean=True)
    @admin.display(description="Error")
    def has_error(self, obj):
        """Show if processing has an error."""
        return obj.processing_error is not None or obj.cog_error is not None

    def get_queryset(self, request):
        """Optimize queryset with related fields."""
        return super().get_queryset(request).select_related("capture__owner")
