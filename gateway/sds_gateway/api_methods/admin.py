from django.contrib import admin

from sds_gateway.api_methods import models


# Register your models here.
@admin.register(models.File)
class FileAdmin(admin.ModelAdmin[models.File]):
    list_display = ("name", "media_type", "size", "owner", "is_deleted")
    search_fields = ("checksum", "name", "media_type", "owner")
    ordering = ("-updated_at",)


@admin.register(models.Capture)
class CaptureAdmin(admin.ModelAdmin[models.Capture]):
    list_display = ("channel", "capture_type", "index_name")
    search_fields = ("uuid", "channel", "index_name")
    list_filter = ("channel", "capture_type", "index_name")
    ordering = ("-updated_at",)


@admin.register(models.Dataset)
class DatasetAdmin(admin.ModelAdmin[models.Dataset]):
    list_display = ("name", "doi")
    search_fields = ("name", "doi")
    ordering = ("-updated_at",)
