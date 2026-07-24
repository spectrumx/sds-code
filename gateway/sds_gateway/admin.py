"""Custom admin dashboard for the Django admin index page."""

from __future__ import annotations

from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models import Q
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.utils.disk_utils import format_file_size
from sds_gateway.monitoring.models import SystemHealthSnapshot


def _dashboard_context() -> dict[str, object]:
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)

    active_files = File.objects.filter(is_deleted=False)
    active_stats = active_files.aggregate(
        count=Count("uuid"),
        total_size=Sum("size"),
    )

    cleanup_files = File.objects.filter(
        is_deleted=True,
        deleted_at__lt=thirty_days_ago,
    )
    cleanup_stats = cleanup_files.aggregate(
        count=Count("uuid"),
        total_size=Sum("size"),
    )

    user_model = get_user_model()
    top_users = (
        user_model.objects.filter(files__is_deleted=False)
        .annotate(
            total_size=Sum("files__size"),
            file_count=Count("files__uuid"),
        )
        .order_by("-total_size")[:10]
    )

    capture_count = Capture.objects.filter(is_deleted=False).count()
    dataset_count = Dataset.objects.filter(is_deleted=False).count()

    health_payload = SystemHealthSnapshot.latest_snapshot_payload()

    fourteen_days_ago = now - timedelta(days=14)
    recent_users = list(
        user_model.objects.filter(date_joined__gte=fourteen_days_ago)
        .order_by("-date_joined")
        .values("email", "name", "is_active", "is_approved", "date_joined", "pk")
    )

    superusers = list(
        user_model.objects.filter(Q(is_staff=True) | Q(is_superuser=True))
        .order_by("-date_joined")
        .values(
            "email",
            "name",
            "is_active",
            "is_approved",
            "is_staff",
            "is_superuser",
            "pk",
        )
    )

    total_user_count = user_model.objects.count()

    return {
        "active_file_count": active_stats["count"] or 0,
        "active_total_size": (
            format_file_size(active_stats["total_size"])
            if active_stats["total_size"]
            else "0 B"
        ),
        "cleanup_file_count": cleanup_stats["count"] or 0,
        "cleanup_total_size": (
            format_file_size(cleanup_stats["total_size"])
            if cleanup_stats["total_size"]
            else "0 B"
        ),
        "top_users": top_users,
        "capture_count": capture_count,
        "dataset_count": dataset_count,
        "health_payload": health_payload,
        "recent_users": recent_users,
        "superusers": superusers,
        "total_user_count": total_user_count,
        "file_admin_url": reverse("admin:api_methods_file_changelist"),
        "capture_admin_url": reverse("admin:api_methods_capture_changelist"),
        "dataset_admin_url": reverse("admin:api_methods_dataset_changelist"),
        "user_admin_url": reverse("admin:users_user_changelist"),
    }


_original_admin_index = admin.site.index


def _dashboard_index(request, extra_context=None):
    extra_context = extra_context or {}
    extra_context["dashboard"] = _dashboard_context()
    return _original_admin_index(request, extra_context=extra_context)


# Override the default admin site index
admin.site.index = _dashboard_index
admin.site.index_template = "admin/dashboard_index.html"
admin.site.site_header = "SDS Gateway Admin"
admin.site.site_title = "SDS Gateway Admin"
admin.site.index_title = "Dashboard"
