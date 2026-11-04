"""Staff workflow after verification/publish on federation sync (no gateway HTTP)."""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus


@dataclass(frozen=True, slots=True)
class StaffOpResult:
    ok: bool
    message: str


@transaction.atomic
def record_manifest_published(*, serial: int) -> StaffOpResult:
    """Staff: sync publish completed; mark approved applications published."""
    if serial < 0:
        return StaffOpResult(ok=False, message="Manifest serial must be non-negative.")
    pending = list(
        RegistryApplication.objects.filter(
            status=RegistryApplicationStatus.APPROVED.value,
        ).exclude(site_name="")
    )
    if not pending:
        return StaffOpResult(
            ok=False,
            message="No approved applications with a site id to mark published.",
        )
    now = timezone.now()
    for application in pending:
        application.status = RegistryApplicationStatus.PUBLISHED.value
        application.published_manifest_serial = serial
        application.published_at = now
    RegistryApplication.objects.bulk_update(
        pending,
        ["status", "published_manifest_serial", "published_at"],
    )
    count = len(pending)
    word = "application" if count == 1 else "applications"
    return StaffOpResult(
        ok=True,
        message=(
            f"Recorded manifest serial {serial}; marked {count} approved "
            f"{word} as published."
        ),
    )
