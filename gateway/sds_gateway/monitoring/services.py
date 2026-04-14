from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.db import connections
from django.db import transaction
from django.utils import timezone

from sds_gateway.monitoring.models import HealthStatus
from sds_gateway.monitoring.models import ServiceCheck
from sds_gateway.monitoring.models import SystemHealthSnapshot

if TYPE_CHECKING:
    import datetime as dt


SERVICE_CHECK_RETENTION_DAYS: int = 180


@dataclass(frozen=True)
class ServiceDefinition:
    name: str
    kind: str
    host: str | None = None
    port: int | None = None


@dataclass(frozen=True)
class ServiceCheckResult:
    service_name: str
    status: str
    latency_ms: int | None
    detail: str = ""


def _split_host_port(endpoint: str, *, default_port: int) -> tuple[str, int]:
    parsed = urlparse(endpoint if "://" in endpoint else f"//{endpoint}")
    host = parsed.hostname or endpoint
    port = parsed.port or default_port
    return host, port


def get_default_service_definitions() -> list[ServiceDefinition]:
    sfs_host, sfs_port = _split_host_port(
        settings.SFS_ENDPOINT_URL,
        default_port=8333,
    )
    minio_host, minio_port = _split_host_port(
        settings.MINIO_ENDPOINT_URL,
        default_port=9000,
    )
    db_config = settings.DATABASES.get("default", {})
    postgres_host = str(db_config.get("HOST", "")).strip() or None
    postgres_port_raw = db_config.get("PORT")
    postgres_port = (
        int(str(postgres_port_raw))
        if postgres_port_raw is not None and str(postgres_port_raw).isdigit()
        else None
    )

    return [
        ServiceDefinition(name="seaweedfs", kind="tcp", host=sfs_host, port=sfs_port),
        ServiceDefinition(name="minio", kind="tcp", host=minio_host, port=minio_port),
        ServiceDefinition(
            name="postgres",
            kind="db",
            host=postgres_host,
            port=postgres_port,
        ),
    ]


def get_service_definitions() -> list[ServiceDefinition]:
    services = list(get_default_service_definitions())
    for extra_service in getattr(settings, "SERVICE_MONITOR_EXTRA_SERVICES", []):
        if not isinstance(extra_service, dict):
            continue
        name = str(extra_service.get("name", "")).strip()
        if not name:
            continue
        kind = str(extra_service.get("kind", "tcp")).strip() or "tcp"
        host = extra_service.get("host")
        port = extra_service.get("port")
        services.append(
            ServiceDefinition(
                name=name,
                kind=kind,
                host=str(host) if host is not None else None,
                port=int(port)
                if isinstance(port, (int, str)) and str(port).isdigit()
                else None,
            )
        )
    return services


def compute_overall_status(check_results: list[ServiceCheckResult]) -> str:
    if not check_results:
        return HealthStatus.DEGRADED
    statuses = {check_result.status for check_result in check_results}
    if HealthStatus.DOWN in statuses:
        return HealthStatus.DOWN
    if HealthStatus.DEGRADED in statuses:
        return HealthStatus.DEGRADED
    return HealthStatus.HEALTHY


def _check_tcp_service(
    service: ServiceDefinition, timeout_seconds: float = 1.0
) -> ServiceCheckResult:
    if service.host is None or service.port is None:
        return ServiceCheckResult(
            service_name=service.name,
            status=HealthStatus.DEGRADED,
            latency_ms=None,
            detail="missing host/port",
        )
    start = time.perf_counter()
    try:
        with socket.create_connection(
            (service.host, service.port), timeout=timeout_seconds
        ):
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ServiceCheckResult(
                service_name=service.name,
                status=HealthStatus.HEALTHY,
                latency_ms=latency_ms,
            )
    except OSError as exc:
        return ServiceCheckResult(
            service_name=service.name,
            status=HealthStatus.DOWN,
            latency_ms=None,
            detail=str(exc),
        )


def _check_default_database(service_name: str = "postgres") -> ServiceCheckResult:
    start = time.perf_counter()
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        latency_ms = int((time.perf_counter() - start) * 1000)
        return ServiceCheckResult(
            service_name=service_name,
            status=HealthStatus.HEALTHY,
            latency_ms=latency_ms,
        )
    except Exception as exc:  # noqa: BLE001
        return ServiceCheckResult(
            service_name=service_name,
            status=HealthStatus.DOWN,
            latency_ms=None,
            detail=str(exc),
        )


def check_service(service: ServiceDefinition) -> ServiceCheckResult:
    if service.kind == "db":
        return _check_default_database(service_name=service.name)
    return _check_tcp_service(service)


def _merge_child_statuses(check_results: list[ServiceCheckResult]) -> dict[str, str]:
    status_priority: dict[str, int] = {
        HealthStatus.HEALTHY: 0,
        HealthStatus.DEGRADED: 1,
        HealthStatus.DOWN: 2,
    }
    merged: dict[str, str] = {}
    for result in sorted(
        check_results,
        key=lambda service_check_result: service_check_result.service_name,
    ):
        current_status = merged.get(result.service_name)
        if (
            current_status is None
            or status_priority[result.status] > status_priority[current_status]
        ):
            merged[result.service_name] = result.status
    return merged


def record_service_checks(
    service_definitions: list[ServiceDefinition] | None = None,
    *,
    checked_at: dt.datetime | None = None,
    checker: Any = check_service,
) -> dict[str, Any]:
    at = checked_at or timezone.now()
    definitions = service_definitions or get_service_definitions()
    check_results = [checker(service) for service in definitions]

    check_records = []
    for definition, result in zip(definitions, check_results, strict=True):
        check_records.append(
            ServiceCheck(
                service_name=result.service_name,
                host=definition.host or "",
                port=definition.port,
                status=result.status,
                checked_at=at,
                latency_ms=result.latency_ms,
                detail=result.detail,
            )
        )
    child_statuses = _merge_child_statuses(check_results)
    overall_status = compute_overall_status(check_results)

    with transaction.atomic():
        ServiceCheck.objects.bulk_create(check_records)
        SystemHealthSnapshot.objects.create(
            checked_at=at,
            overall_status=overall_status,
            child_statuses=child_statuses,
        )

    return {
        "checked_at": at,
        "overall_status": overall_status,
        "child_statuses": child_statuses,
    }


def prune_old_service_checks(
    *,
    now: dt.datetime | None = None,
    retention_days: int = SERVICE_CHECK_RETENTION_DAYS,
) -> int:
    cutoff = (now or timezone.now()) - timedelta(days=retention_days)
    deleted_count, _ = ServiceCheck.objects.filter(checked_at__lt=cutoff).delete()
    return deleted_count
