from datetime import timedelta
from typing import cast

import pytest
from django.contrib.admin.sites import AdminSite
from django.db import connection
from django.template.loader import render_to_string
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.status import HTTP_200_OK

from sds_gateway.monitoring.admin import SystemHealthSnapshotAdmin
from sds_gateway.monitoring.models import HealthStatus
from sds_gateway.monitoring.models import ServiceCheck
from sds_gateway.monitoring.models import SystemHealthSnapshot
from sds_gateway.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_monitoring_dashboard_changelist_is_available(client) -> None:
    admin_user = UserFactory(is_staff=True, is_superuser=True)
    client.force_login(admin_user)

    checked_at = timezone.now()
    SystemHealthSnapshot.objects.create(
        checked_at=checked_at,
        overall_status=HealthStatus.DEGRADED,
        child_statuses={
            "primary-storage": HealthStatus.DOWN,
            "postgres": HealthStatus.HEALTHY,
        },
    )
    ServiceCheck.objects.create(
        service_name="primary-storage",
        host="localhost",
        port=9000,
        status=HealthStatus.HEALTHY,
        checked_at=checked_at,
        latency_ms=5,
        detail="",
    )

    response = client.get(reverse("admin:monitoring_systemhealthsnapshot_changelist"))

    assert response.status_code == HTTP_200_OK
    assert b"Monitoring dashboard" in response.content
    assert b"Service trend" in response.content
    assert b"Last checked" in response.content
    assert b"admin-monitoring-pill--healthy" in response.content


def test_admin_base_template_shows_global_status(rf) -> None:
    SystemHealthSnapshot.objects.create(
        checked_at=timezone.now(),
        overall_status=HealthStatus.HEALTHY,
        child_statuses={
            "seaweedfs": HealthStatus.HEALTHY,
            "minio": HealthStatus.HEALTHY,
            "postgres": HealthStatus.HEALTHY,
        },
    )

    request = rf.get("/admin/")
    rendered = render_to_string("admin/base_site.html", request=request)

    assert "overall: healthy" in rendered.lower()
    assert "seaweedfs" in rendered.lower()
    assert "postgres" in rendered.lower()


def test_dashboard_context_avoids_n_plus_one_queries() -> None:
    checked_at = timezone.now()
    checks = []
    num_services: int = 5
    num_queries: int = (
        3  # 1 for snapshot + 2 for checks (fetching latest and recent separately)
    )
    for service_number in range(num_services):
        service_name = f"service-{service_number}"
        checks.extend(
            ServiceCheck(
                service_name=service_name,
                status=HealthStatus.HEALTHY,
                checked_at=checked_at,
                latency_ms=sample,
                detail="",
            )
            for sample in range(35)
        )
    ServiceCheck.objects.bulk_create(checks)

    model_admin = SystemHealthSnapshotAdmin(SystemHealthSnapshot, AdminSite())
    with CaptureQueriesContext(connection) as queries:
        dashboard = model_admin._dashboard_context()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    trend_services = cast("list[dict[str, object]]", dashboard["trend_services"])

    assert len(trend_services) == num_services
    assert len(queries) <= num_queries


def test_dashboard_context_splits_trends_by_service_host_and_port() -> None:
    checked_at = timezone.now()
    ServiceCheck.objects.bulk_create(
        [
            ServiceCheck(
                service_name="seaweedfs",
                host="sfs-a.local",
                port=8333,
                status=HealthStatus.HEALTHY,
                checked_at=checked_at,
                latency_ms=5,
                detail="",
            ),
            ServiceCheck(
                service_name="seaweedfs",
                host="sfs-b.local",
                port=8333,
                status=HealthStatus.DOWN,
                checked_at=checked_at,
                latency_ms=None,
                detail="refused",
            ),
        ]
    )

    model_admin = SystemHealthSnapshotAdmin(SystemHealthSnapshot, AdminSite())
    dashboard = model_admin._dashboard_context()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    trend_services = cast("list[dict[str, object]]", dashboard["trend_services"])

    num_services: int = 2
    assert len(trend_services) == num_services
    assert {
        (row["service_name"], row["host"], row["port"], row["latest_status"])
        for row in trend_services
    } == {
        ("seaweedfs", "sfs-a.local", 8333, HealthStatus.HEALTHY),
        ("seaweedfs", "sfs-b.local", 8333, HealthStatus.DOWN),
    }


def test_dashboard_context_omits_services_with_stale_latest_check() -> None:
    now = timezone.now()
    ServiceCheck.objects.bulk_create(
        [
            ServiceCheck(
                service_name="postgres",
                host="db.local",
                port=5432,
                status=HealthStatus.HEALTHY,
                checked_at=now - timedelta(minutes=30),
                latency_ms=5,
                detail="",
            ),
            ServiceCheck(
                service_name="primary-storage",
                host="sfs.local",
                port=8333,
                status=HealthStatus.DOWN,
                checked_at=now - timedelta(hours=2),
                latency_ms=None,
                detail="timeout",
            ),
        ]
    )

    model_admin = SystemHealthSnapshotAdmin(SystemHealthSnapshot, AdminSite())
    dashboard = model_admin._dashboard_context()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    trend_services = cast("list[dict[str, object]]", dashboard["trend_services"])

    assert len(trend_services) == 1
    assert trend_services[0]["service_name"] == "postgres"
    assert trend_services[0]["latest_checked_at"] == now - timedelta(minutes=30)


def test_dashboard_context_orders_trend_services_by_latest_check() -> None:
    now = timezone.now()
    ServiceCheck.objects.bulk_create(
        [
            ServiceCheck(
                service_name="postgres",
                host="db.local",
                port=5432,
                status=HealthStatus.HEALTHY,
                checked_at=now - timedelta(minutes=10),
                latency_ms=5,
                detail="",
            ),
            ServiceCheck(
                service_name="primary-storage",
                host="sfs.local",
                port=8333,
                status=HealthStatus.HEALTHY,
                checked_at=now - timedelta(minutes=1),
                latency_ms=5,
                detail="",
            ),
            ServiceCheck(
                service_name="opensearch",
                host="search.local",
                port=9200,
                status=HealthStatus.DOWN,
                checked_at=now - timedelta(minutes=5),
                latency_ms=None,
                detail="timeout",
            ),
        ]
    )

    model_admin = SystemHealthSnapshotAdmin(SystemHealthSnapshot, AdminSite())
    dashboard = model_admin._dashboard_context()  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
    trend_services = cast("list[dict[str, object]]", dashboard["trend_services"])

    assert [row["service_name"] for row in trend_services] == [
        "primary-storage",
        "opensearch",
        "postgres",
    ]
