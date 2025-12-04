from django.contrib import admin

from sds_gateway.api_methods import models


# Register your models here.
@admin.register(models.File)
class FileAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    list_display = ("name", "media_type", "size", "owner", "is_deleted")
    search_fields = ("checksum", "name", "media_type", "owner")
    ordering = ("-updated_at",)


@admin.register(models.Capture)
class CaptureAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    list_display = ("name", "channel", "capture_type", "index_name")
    search_fields = ("uuid", "name", "channel", "index_name")
    list_filter = ("channel", "capture_type", "index_name")
    ordering = ("-updated_at",)


@admin.register(models.Dataset)
class DatasetAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    list_display = ("name", "doi", "get_keywords", "status", "owner")
    search_fields = ("name", "doi", "keywords__name", "owner__email")
    list_filter = ("status", "keywords")
    ordering = ("-updated_at",)

    @admin.display(description="Keywords")
    def get_keywords(self, obj):
        """Display comma-separated list of keywords."""
        keywords = obj.keywords.filter(is_deleted=False)
        if keywords.exists():
            return ", ".join([kw.name for kw in keywords[:5]])
        return "-"


@admin.register(models.TemporaryZipFile)
class TemporaryZipFileAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    list_display = ("uuid", "owner", "created_at", "expires_at")
    search_fields = ("uuid", "owner")
    ordering = ("-created_at",)


@admin.register(models.UserSharePermission)
class UserSharePermissionAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    list_display = ("item_uuid", "item_type", "shared_with", "owner", "is_enabled")
    search_fields = ("item_uuid", "item_type", "shared_with", "owner")
    list_filter = ("item_type", "is_enabled")
    ordering = ("-updated_at",)


@admin.register(models.DEPRECATEDPostProcessedData)
class PostProcessedDataAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    list_display = (
        "processing_type",
        "capture",
        "processing_status",
        "processed_at",
        "pipeline_id",
    )
    search_fields = ("uuid", "processing_type", "capture__name", "pipeline_id")
    list_filter = ("processing_type", "processing_status", "processed_at")
    readonly_fields = ("uuid", "created_at", "updated_at", "processed_at")
    ordering = ("-created_at",)
    fieldsets = (
        (
            "Basic Information",
            {"fields": ("uuid", "capture", "processing_type", "processing_status")},
        ),
        (
            "Processing Details",
            {
                "fields": (
                    "processing_parameters",
                    "pipeline_id",
                    "processed_at",
                )
            },
        ),
        (
            "Data & Metadata",
            {"fields": ("data_file", "metadata", "processing_error")},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(models.ShareGroup)
class ShareGroupAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    list_display = ("name", "owner")
    search_fields = ("name", "owner")
    ordering = ("-updated_at",)


@admin.register(models.Keyword)
class KeywordAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    list_display = ("name", "get_datasets", "created_at")
    search_fields = ("name", "datasets__name")
    list_filter = ("datasets",)
    ordering = ("name",)

    @admin.display(description="Datasets")
    def get_datasets(self, obj):
        """Display comma-separated list of dataset names."""
        return ", ".join([dataset.name for dataset in obj.datasets.all()[:3]])
