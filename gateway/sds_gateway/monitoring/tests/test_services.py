from datetime import timedelta

import pytest
from django.utils import timezone

from sds_gateway.monitoring.models import HealthStatus
from sds_gateway.monitoring.models import ServiceCheck
from sds_gateway.monitoring.models import SystemHealthSnapshot
from sds_gateway.monitoring.services import ServiceCheckResult
from sds_gateway.monitoring.services import ServiceDefinition
from sds_gateway.monitoring.services import compute_overall_status
from sds_gateway.monitoring.services import get_default_service_definitions
from sds_gateway.monitoring.services import prune_old_service_checks
from sds_gateway.monitoring.services import record_service_checks

pytestmark = pytest.mark.django_db


def test_compute_overall_status_is_down_if_any_service_is_down() -> None:
    result = compute_overall_status(
        [
            ServiceCheckResult("seaweedfs", HealthStatus.HEALTHY, 11),
            ServiceCheckResult("postgres", HealthStatus.DOWN, None),
        ]
    )

    assert result == HealthStatus.DOWN


def test_default_services_include_core_dependencies() -> None:
    service_names = {
        service_definition.name
        for service_definition in get_default_service_definitions()
    }

    assert service_names == {"seaweedfs", "minio", "postgres"}


def test_record_service_checks_persists_history_and_snapshot() -> None:
    checks_at = timezone.now()

    def fake_checker(service: ServiceDefinition) -> ServiceCheckResult:
        if service.name == "minio":
            return ServiceCheckResult(
                "minio", HealthStatus.DOWN, None, "connection refused"
            )
        return ServiceCheckResult(service.name, HealthStatus.HEALTHY, 5)

    services = [
        ServiceDefinition(name="seaweedfs", kind="tcp", host="localhost", port=1),
        ServiceDefinition(name="minio", kind="tcp", host="localhost", port=1),
        ServiceDefinition(name="postgres", kind="db"),
    ]
    summary = record_service_checks(
        service_definitions=services,
        checked_at=checks_at,
        checker=fake_checker,
    )

    assert ServiceCheck.objects.count() == len(services)
    assert SystemHealthSnapshot.objects.count() == 1
    assert summary["overall_status"] == HealthStatus.DOWN

    saved_checks = {
        (service_check.service_name, service_check.host, service_check.port)
        for service_check in ServiceCheck.objects.all()
    }
    assert saved_checks == {
        ("seaweedfs", "localhost", 1),
        ("minio", "localhost", 1),
        ("postgres", "", None),
    }

    snapshot = SystemHealthSnapshot.objects.get()
    assert snapshot.checked_at == checks_at
    assert snapshot.child_statuses == {
        "minio": HealthStatus.DOWN,
        "postgres": HealthStatus.HEALTHY,
        "seaweedfs": HealthStatus.HEALTHY,
    }


def test_record_service_checks_uses_worst_status_when_service_name_is_duplicated() -> (
    None
):
    checks_at = timezone.now()
    port_to_refuse: int = 2

    def fake_checker(service: ServiceDefinition) -> ServiceCheckResult:
        if service.port == port_to_refuse:
            return ServiceCheckResult(
                service.name, HealthStatus.DOWN, None, "connection refused"
            )
        return ServiceCheckResult(service.name, HealthStatus.HEALTHY, 5)

    services = [
        ServiceDefinition(name="seaweedfs", kind="tcp", host="localhost", port=1),
        ServiceDefinition(
            name="seaweedfs", kind="tcp", host="localhost", port=port_to_refuse
        ),
    ]
    summary = record_service_checks(
        service_definitions=services,
        checked_at=checks_at,
        checker=fake_checker,
    )

    assert ServiceCheck.objects.count() == len(services)
    assert SystemHealthSnapshot.objects.count() == 1
    assert summary["child_statuses"] == {"seaweedfs": HealthStatus.DOWN}


def test_record_service_checks_rolls_back_service_checks_if_snapshot_create_fails(
    monkeypatch,
) -> None:
    checks_at = timezone.now()

    def fake_checker(service: ServiceDefinition) -> ServiceCheckResult:
        return ServiceCheckResult(service.name, HealthStatus.HEALTHY, 5)

    def failing_create(**_kwargs):
        msg = "boom"
        raise RuntimeError(msg)

    monkeypatch.setattr(SystemHealthSnapshot.objects, "create", failing_create)

    with pytest.raises(RuntimeError, match="boom"):
        record_service_checks(
            service_definitions=[
                ServiceDefinition(
                    name="seaweedfs", kind="tcp", host="localhost", port=1
                ),
                ServiceDefinition(name="postgres", kind="db"),
            ],
            checked_at=checks_at,
            checker=fake_checker,
        )

    assert ServiceCheck.objects.count() == 0
    assert SystemHealthSnapshot.objects.count() == 0


def test_prune_old_service_checks_removes_only_records_older_than_retention() -> None:
    now = timezone.now()
    cutoff_days: int = 180
    old_check = ServiceCheck.objects.create(
        service_name="seaweedfs",
        host="sfs.local",
        port=8333,
        status=HealthStatus.HEALTHY,
        checked_at=now - timedelta(days=cutoff_days + 1),
        latency_ms=5,
        detail="",
    )
    kept_check = ServiceCheck.objects.create(
        service_name="seaweedfs",
        host="sfs.local",
        port=8333,
        status=HealthStatus.HEALTHY,
        checked_at=now - timedelta(days=cutoff_days),
        latency_ms=5,
        detail="",
    )

    deleted_count = prune_old_service_checks(now=now)

    assert deleted_count == 1
    assert ServiceCheck.objects.filter(pk=old_check.pk).exists() is False
    assert ServiceCheck.objects.filter(pk=kept_check.pk).exists() is True
