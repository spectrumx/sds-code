import json

from django.contrib import admin
from django.db.models import Count
from django.db.models import OuterRef
from django.db.models import PositiveIntegerField
from django.db.models import Subquery

from sds_gateway.api_methods import models
from sds_gateway.api_methods.utils.disk_utils import format_file_size


# Register your models here.
@admin.register(models.File)
class FileAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    list_display = (
        "name",
        "capture_count",
        "owner",
        "media_type",
        "formatted_size",
        "is_public",
        "is_deleted",
        "expiration_date",
        "created_at",
        "updated_at",
    )
    search_fields = ("sum_blake3", "name", "media_type", "owner__email")
    ordering = ("-updated_at",)

    @admin.display(description="# Cap")
    def capture_count(self, obj):
        count = getattr(obj, "_capture_count", None)
        return count if count is not None else "-"

    @admin.display(description="Size", ordering="size")
    def formatted_size(self, obj):
        return format_file_size(obj.size) if obj.size is not None else "-"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("owner")
            .annotate(_capture_count=Count("captures"))
        )


@admin.register(models.Capture)
class CaptureAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    list_display = (
        "name",
        "dataset_count",
        "owner",
        "capture_type",
        "file_count",
        "origin",
        "channel",
        "index_name",
        "is_deleted",
        "created_at",
        "updated_at",
    )
    search_fields = ("uuid", "name", "channel", "index_name")
    list_filter = ("channel", "capture_type", "index_name")
    ordering = ("-updated_at",)

    @admin.display(description="# Ds")
    def dataset_count(self, obj):
        return getattr(obj, "_dataset_count", None)

    @admin.display(description="Files")
    def file_count(self, obj):
        count = getattr(obj, "_file_count", None)
        return f"{count} files" if count is not None else "-"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("owner")
            .annotate(
                _dataset_count=Subquery(
                    models.Capture.datasets.through.objects.filter(
                        capture_id=OuterRef("pk")
                    )
                    .values("capture_id")
                    .annotate(cnt=Count("id"))
                    .values("cnt")[:1],
                    output_field=PositiveIntegerField(),
                ),
                _file_count=Subquery(
                    models.Capture.files.through.objects.filter(
                        capture_id=OuterRef("pk")
                    )
                    .values("capture_id")
                    .annotate(cnt=Count("id"))
                    .values("cnt")[:1],
                    output_field=PositiveIntegerField(),
                ),
            )
        )


@admin.register(models.Dataset)
class DatasetAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    list_display = (
        "name",
        "owner",
        "status",
        "capture_count",
        "file_count",
        "version",
        "doi",
        "get_keywords",
        "license",
        "release_date",
        "is_deleted",
        "created_at",
        "updated_at",
    )
    search_fields = ("name", "doi", "keywords__name", "owner__email")
    list_filter = ("status", "keywords")
    ordering = ("-updated_at",)

    @admin.display(description="# Cap")
    def capture_count(self, obj):
        count = getattr(obj, "_capture_count", None)
        return f"{count} captures" if count is not None else "-"

    @admin.display(description="Artifact Files")
    def file_count(self, obj):
        count = getattr(obj, "_file_count", None)
        return f"{count} artifact files" if count is not None else "-"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("owner")
            .annotate(
                _capture_count=Subquery(
                    models.Dataset.captures.through.objects.filter(
                        dataset_id=OuterRef("pk")
                    )
                    .values("dataset_id")
                    .annotate(cnt=Count("id"))
                    .values("cnt")[:1],
                    output_field=PositiveIntegerField(),
                ),
                _file_count=Subquery(
                    models.Dataset.files.through.objects.filter(
                        dataset_id=OuterRef("pk")
                    )
                    .values("dataset_id")
                    .annotate(cnt=Count("id"))
                    .values("cnt")[:1],
                    output_field=PositiveIntegerField(),
                ),
            )
        )

    @admin.display(description="Keywords")
    def get_keywords(self, obj):
        """Display comma-separated list of keywords."""
        keywords = obj.keywords.filter(is_deleted=False)
        if keywords.exists():
            return ", ".join([kw.name for kw in keywords[:5]])
        return "-"

    def save_model(self, request, obj, form, change):
        """Override save_model to handle list fields."""
        for field_name in models.Dataset.list_fields:
            field_value = getattr(obj, field_name, None)

            if field_value is None or field_value == "":
                setattr(obj, field_name, [])
            elif isinstance(field_value, str):
                try:
                    parsed_value = json.loads(field_value)
                    if isinstance(parsed_value, list):
                        setattr(obj, field_name, parsed_value)
                    else:
                        setattr(obj, field_name, [parsed_value])
                except (json.JSONDecodeError, TypeError):
                    if "," in field_value:
                        # Split by comma and strip whitespace
                        setattr(
                            obj,
                            field_name,
                            [
                                item.strip()
                                for item in field_value.split(",")
                                if item.strip()
                            ],
                        )
                    else:
                        # Single value, wrap in list
                        setattr(
                            obj,
                            field_name,
                            [field_value.strip()] if field_value.strip() else [],
                        )

        super().save_model(request, obj, form, change)


@admin.register(models.TemporaryZipFile)
class TemporaryZipFileAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    list_display = (
        "filename",
        "owner",
        "formatted_file_size",
        "creation_status",
        "is_downloaded",
        "created_at",
        "expires_at",
    )
    search_fields = ("uuid", "owner__email")
    ordering = ("-created_at",)

    @admin.display(description="File Size", ordering="file_size")
    def formatted_file_size(self, obj):
        return format_file_size(obj.file_size) if obj.file_size is not None else "-"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("owner")


@admin.register(models.UserSharePermission)
class UserSharePermissionAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    list_display = (
        "owner",
        "shared_with",
        "item_type",
        "item_name",
        "permission_level",
        "notified",
        "is_enabled",
        "created_at",
    )
    search_fields = ("item_uuid", "item_type", "shared_with__email", "owner__email")
    list_filter = ("item_type", "is_enabled")
    ordering = ("-updated_at",)

    @admin.display(description="Item Name")
    def item_name(self, obj):
        """Resolve item_uuid to the actual dataset/capture name.

        Note: UserSharePermission uses item_type + item_uuid (UUID polymorphic),
        not FK relations, so Prefetch/select_related can't batch-load items.
        Consider denormalizing item_name onto the model if N+1 becomes a problem.
        """
        from sds_gateway.api_methods.models import Capture
        from sds_gateway.api_methods.models import Dataset
        from sds_gateway.api_methods.models import ItemType

        if obj.item_type == ItemType.DATASET:
            item = Dataset.objects.filter(uuid=obj.item_uuid).first()
            return item.name if item else str(obj.item_uuid)
        if obj.item_type == ItemType.CAPTURE:
            item = Capture.objects.filter(uuid=obj.item_uuid).first()
            return item.name if item else str(obj.item_uuid)
        return str(obj.item_uuid)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("owner", "shared_with")


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
    list_display = ("name", "owner", "member_count", "created_at", "updated_at")
    search_fields = ("name", "owner__email")
    ordering = ("-updated_at",)

    @admin.display(description="Members", ordering="_member_count")
    def member_count(self, obj):
        return getattr(obj, "_member_count", "-")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("owner")
            .annotate(_member_count=Count("group_share_permissions"))
        )


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
