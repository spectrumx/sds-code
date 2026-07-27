"""Custom admin dashboard for the Django admin index page."""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.db import OperationalError
from django.db import ProgrammingError
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

logger = logging.getLogger(__name__)

_DASHBOARD_FALLBACK: dict[str, object] = {
    "active_file_count": 0,
    "active_total_size": "0 B",
    "cleanup_file_count": 0,
    "cleanup_total_size": "0 B",
    "top_users": [],
    "capture_count": 0,
    "dataset_count": 0,
    "health_payload": None,
    "recent_users": [],
    "superusers": [],
    "total_user_count": 0,
    "file_admin_url": "#",
    "capture_admin_url": "#",
    "dataset_admin_url": "#",
    "user_admin_url": "#",
}


def _file_stats() -> dict[str, object]:
    """Return file-related stats for the dashboard."""
    now = timezone.now()
    thirty_days_ago = now - timedelta(days=30)

    active_stats = File.objects.filter(is_deleted=False).aggregate(
        count=Count("uuid"),
        total_size=Sum("size"),
    )
    cleanup_stats = File.objects.filter(
        is_deleted=True,
        deleted_at__lt=thirty_days_ago,
    ).aggregate(
        count=Count("uuid"),
        total_size=Sum("size"),
    )
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
    }


def _capture_dataset_stats() -> dict[str, int]:
    """Return capture and dataset counts for the dashboard."""
    return {
        "capture_count": Capture.objects.filter(is_deleted=False).count(),
        "dataset_count": Dataset.objects.filter(is_deleted=False).count(),
    }


def _user_stats() -> dict[str, object]:
    """Return user-related stats for the dashboard."""
    user_model = get_user_model()
    now = timezone.now()
    fourteen_days_ago = now - timedelta(days=14)

    top_users = list(
        user_model.objects.filter(files__is_deleted=False)
        .annotate(
            total_size=Sum("files__size", default=0),
            file_count=Count("files__uuid"),
        )
        .order_by("-total_size")[:10]
    )
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
    return {
        "top_users": top_users,
        "recent_users": recent_users,
        "superusers": superusers,
        "total_user_count": user_model.objects.count(),
    }


def _system_health() -> dict[str, object]:
    """Return system health snapshot for the dashboard."""
    return {"health_payload": SystemHealthSnapshot.latest_snapshot_payload()}


def _dashboard_context() -> dict[str, object]:
    try:
        ctx: dict[str, object] = {}
        ctx.update(_file_stats())
        ctx.update(_capture_dataset_stats())
        ctx.update(_user_stats())
        ctx.update(_system_health())
        ctx["file_admin_url"] = reverse("admin:api_methods_file_changelist")
        ctx["capture_admin_url"] = reverse("admin:api_methods_capture_changelist")
        ctx["dataset_admin_url"] = reverse("admin:api_methods_dataset_changelist")
        ctx["user_admin_url"] = reverse("admin:users_user_changelist")
    except (OperationalError, ProgrammingError, DatabaseError):
        logger.exception("Dashboard context query failed")
        return deepcopy(_DASHBOARD_FALLBACK)
    return ctx


# TODO: Replace monkey-patch with AdminSite subclass.
# Subclassing requires changing config/urls.py to use the custom site instance
# instead of the default admin.site. For now, monkey-patch the index method
# to inject dashboard context. Fragile if Django changes AdminSite internals.
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
