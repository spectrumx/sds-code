from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.contrib import admin
from django.utils import timezone

if TYPE_CHECKING:
    from django.db.models import QuerySet

from sds_gateway.monitoring.models import HealthStatus
from sds_gateway.monitoring.models import ServiceCheck
from sds_gateway.monitoring.models import SystemHealthSnapshot


@admin.register(ServiceCheck)
class ServiceCheckAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    list_display = (
        "service_name",
        "host",
        "port",
        "status",
        "checked_at",
        "latency_ms",
        "detail",
    )
    search_fields = ("service_name", "host", "detail")
    list_filter = ("service_name", "status", "checked_at", "port")
    ordering = ("-checked_at", "service_name", "host", "port")


@admin.register(SystemHealthSnapshot)
class SystemHealthSnapshotAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    change_list_template = "admin/monitoring/systemhealthsnapshot/change_list.html"
    list_display = ("checked_at", "overall_status", "services_summary")
    list_filter = ("overall_status", "checked_at")
    ordering = ("-checked_at",)
    readonly_fields = ("checked_at", "overall_status", "child_statuses")

    @admin.display(description="Services")
    def services_summary(self, obj: SystemHealthSnapshot) -> str:
        parts = [
            f"{service}:{status}"
            for service, status in sorted(obj.child_statuses.items())
        ]
        return ", ".join(parts)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["monitoring_dashboard"] = self._dashboard_context()
        return super().changelist_view(request, extra_context=extra_context)

    def _dashboard_context(self) -> dict[str, object]:
        latest_snapshot = SystemHealthSnapshot.objects.first()
        num_hours_uptime_window: int = 3
        num_hours_recent_check_window: int = 1
        now = timezone.now()
        uptime_window_start = now - timedelta(hours=num_hours_uptime_window)
        recent_check_cutoff = now - timedelta(hours=num_hours_recent_check_window)
        checks: QuerySet[ServiceCheck] = ServiceCheck.objects.filter(
            checked_at__gte=uptime_window_start
        ).order_by("service_name", "host", "port", "-checked_at")

        grouped_checks: dict[tuple[str, str, int | None], list[ServiceCheck]] = {}
        for check in checks:
            grouping_key = (check.service_name, check.host, check.port)
            grouped_checks.setdefault(grouping_key, []).append(check)

        trend_services: list[dict[str, object]] = []
        for service_name, host, port in sorted(grouped_checks):
            recent_checks = grouped_checks[(service_name, host, port)]
            latest_check = recent_checks[0]
            if latest_check.checked_at < recent_check_cutoff:
                continue
            up_count = sum(
                1 for check in recent_checks if check.status == HealthStatus.HEALTHY
            )
            uptime_percent_3h = round((up_count / len(recent_checks)) * 100, 1)
            trend_services.append(
                {
                    "service_name": service_name,
                    "host": host,
                    "port": port,
                    "latest_status": latest_check.status,
                    "latest_checked_at": latest_check.checked_at,
                    "uptime_percent_3h": uptime_percent_3h,
                    "samples": len(recent_checks),
                }
            )

        trend_services.sort(
            key=lambda row: row["latest_checked_at"],
            reverse=True,
        )

        return {
            "latest_snapshot": latest_snapshot,
            "trend_services": trend_services,
        }
