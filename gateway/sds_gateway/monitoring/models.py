from __future__ import annotations

from typing import Any

from django.db import models


class HealthStatus(models.TextChoices):
    HEALTHY = "healthy", "Healthy"
    DEGRADED = "degraded", "Degraded"
    DOWN = "down", "Down"


class ServiceCheck(models.Model):
    service_name = models.CharField(max_length=64, db_index=True)
    host = models.CharField(max_length=255, blank=True)
    port = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=HealthStatus.choices)
    checked_at = models.DateTimeField(db_index=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    detail = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-checked_at", "service_name"]
        indexes = [
            models.Index(fields=["service_name", "-checked_at"]),
            models.Index(fields=["status", "-checked_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.service_name}={self.status} @ {self.checked_at.isoformat()}"


class SystemHealthSnapshot(models.Model):
    checked_at = models.DateTimeField(db_index=True)
    overall_status = models.CharField(max_length=16, choices=HealthStatus.choices)
    child_statuses = models.JSONField(default=dict)

    class Meta:
        ordering = ["-checked_at"]

    def __str__(self) -> str:
        return f"system={self.overall_status} @ {self.checked_at.isoformat()}"

    def normalized_child_statuses(self) -> list[dict[str, str]]:
        if not isinstance(self.child_statuses, dict):
            return []
        normalized: list[dict[str, str]] = []
        for service_name, status in sorted(self.child_statuses.items()):
            normalized.append(
                {
                    "service_name": str(service_name),
                    "status": str(status),
                }
            )
        return normalized

    @classmethod
    def latest_snapshot_payload(cls) -> dict[str, Any] | None:
        snapshot = cls.objects.only(
            "checked_at",
            "overall_status",
            "child_statuses",
        ).first()
        if snapshot is None:
            return None
        return {
            "checked_at": snapshot.checked_at,
            "overall_status": snapshot.overall_status,
            "child_statuses": snapshot.normalized_child_statuses(),
        }
