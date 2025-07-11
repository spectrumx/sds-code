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
