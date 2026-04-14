from celery import shared_task

from sds_gateway.monitoring.services import prune_old_service_checks
from sds_gateway.monitoring.services import record_service_checks


@shared_task
def monitor_services_health() -> dict[str, object]:
    summary = record_service_checks()
    deleted_checks = prune_old_service_checks()
    summary["deleted_old_checks"] = deleted_checks
    return summary
