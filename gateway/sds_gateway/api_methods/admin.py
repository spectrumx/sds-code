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
    list_display = ("name", "doi")
    search_fields = ("name", "doi")
    ordering = ("-updated_at",)


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


@admin.register(models.PostProcessedData)
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
                    "pipeline_step",
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
