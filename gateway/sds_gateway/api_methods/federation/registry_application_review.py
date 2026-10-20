from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.utils import timezone

from sds_gateway.api_methods.federation.registry_application_verify import (
    _backfill_urls_from_well_known,
)
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus

if TYPE_CHECKING:
    from sds_gateway.users.models import User

_APPROVABLE_STATUS = RegistryApplicationStatus.PENDING_APPROVAL.value

_SITE_NAME_RESERVED_STATUSES = (
    RegistryApplicationStatus.APPROVED.value,
    RegistryApplicationStatus.PUBLISHED.value,
)


@dataclass(frozen=True, slots=True)
class ReviewResult:
    ok: bool
    message: str


def _resolve_site_name(
    application: RegistryApplication, override: str | None = None
) -> str:
    raw = override or application.site_name or application.proposed_site_name or ""
    site_name = raw.strip()
    if not site_name:
        msg = "site_name is required (set on the application or use proposed site id)."
        raise ValueError(msg)
    return site_name


def site_name_taken(site_name: str, *, exclude_pk: str | None = None) -> bool:
    qs = RegistryApplication.objects.filter(
        site_name=site_name,
        status__in=_SITE_NAME_RESERVED_STATUSES,
    )
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def approve_registry_application(
    application: RegistryApplication,
    reviewer: User,
    *,
    site_name: str | None = None,
) -> ReviewResult:
    if application.status != _APPROVABLE_STATUS:
        return ReviewResult(
            ok=False,
            message="Only applications awaiting approval can be approved.",
        )

    try:
        assigned_name = _resolve_site_name(application, site_name)
    except ValueError as exc:
        return ReviewResult(ok=False, message=str(exc))

    if site_name_taken(assigned_name, exclude_pk=str(application.pk)):
        return ReviewResult(
            ok=False,
            message=f"site_name '{assigned_name}' is already assigned to an approved site.",
        )

    application.site_name = assigned_name
    application.status = RegistryApplicationStatus.APPROVED.value
    application.reviewed_by = reviewer
    application.reviewed_at = timezone.now()
    application.rejected_reason = ""

    update_fields = [
        "site_name",
        "status",
        "reviewed_by",
        "reviewed_at",
        "rejected_reason",
    ]
    if application.verified_well_known:
        update_fields.extend(
            _backfill_urls_from_well_known(application, application.verified_well_known)
        )

    application.save(update_fields=list(dict.fromkeys(update_fields)))
    return ReviewResult(
        ok=True,
        message=f"Approved {application.fqdn} as site '{assigned_name}'.",
    )


def reject_registry_application(
    application: RegistryApplication,
    reviewer: User,
    *,
    reason: str = "",
) -> ReviewResult:
    if application.status != _APPROVABLE_STATUS:
        return ReviewResult(
            ok=False,
            message="Only applications awaiting approval can be rejected.",
        )

    application.status = RegistryApplicationStatus.REJECTED.value
    application.reviewed_by = reviewer
    application.reviewed_at = timezone.now()
    application.rejected_reason = (reason or "").strip()
    application.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "rejected_reason"]
    )
    return ReviewResult(
        ok=True, message=f"Rejected application for {application.fqdn}."
    )
