import pytest

from sds_gateway.monitoring.tasks import monitor_services_health

pytestmark = pytest.mark.django_db


def test_monitor_services_health_task_calls_recorder(monkeypatch) -> None:
    called = {"record": False, "prune": False}

    num_old_checks: int = 7

    def fake_record_service_checks() -> dict[str, str]:
        called["record"] = True
        return {"overall_status": "healthy"}

    def fake_prune_old_service_checks() -> int:
        called["prune"] = True
        return num_old_checks

    monkeypatch.setattr(
        "sds_gateway.monitoring.tasks.record_service_checks",
        fake_record_service_checks,
    )
    monkeypatch.setattr(
        "sds_gateway.monitoring.tasks.prune_old_service_checks",
        fake_prune_old_service_checks,
    )

    result = monitor_services_health()

    assert called["record"] is True
    assert called["prune"] is True
    assert result["overall_status"] == "healthy"
    assert result["deleted_old_checks"] == num_old_checks
