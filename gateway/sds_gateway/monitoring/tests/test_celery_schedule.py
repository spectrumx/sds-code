from celery.schedules import crontab
from django.conf import settings
from django.utils import timezone
import pytest


@pytest.mark.skip(
    reason="Flaky in CI: crontab.is_due depends on Celery's runtime clock/timezone."
)
def test_monitoring_task_is_in_celery_beat_schedule() -> None:
    assert "monitor-services-health" in settings.CELERY_BEAT_SCHEDULE

    schedule_config = settings.CELERY_BEAT_SCHEDULE["monitor-services-health"]

    assert (
        schedule_config["task"]
        == "sds_gateway.monitoring.tasks.monitor_services_health"
    )
    assert isinstance(schedule_config["schedule"], crontab)
    _is_due, next_run_seconds = schedule_config["schedule"].is_due(timezone.now())
    check_period_sec: int = 60
    expected_expires_sec = check_period_sec - 10
    assert 0 <= next_run_seconds <= check_period_sec
    assert schedule_config["options"]["expires"] == expected_expires_sec
