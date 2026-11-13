"""Staff notification when a registry application awaits approval."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from loguru import logger

from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus

if TYPE_CHECKING:
    import uuid

_PLAIN_TEMPLATE = "emails/registry_application_pending_approval.txt"
_HTML_TEMPLATE = "emails/registry_application_pending_approval.html"


def registry_staff_notify_recipients() -> list[str]:
    """Explicit env list, else active staff users, else ADMINS."""
    configured = (
        getattr(settings, "FEDERATION_REGISTRY_STAFF_NOTIFY_EMAILS", None) or []
    )
    emails = sorted({str(addr).strip() for addr in configured if str(addr).strip()})
    if emails:
        return emails

    from sds_gateway.users.models import User

    staff_emails = (
        User.objects.filter(is_staff=True, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    emails = sorted({addr.strip() for addr in staff_emails if str(addr).strip()})
    if emails:
        return emails

    return sorted(
        {str(addr).strip() for _name, addr in settings.ADMINS if str(addr).strip()}
    )


def _application_detail_url(application: RegistryApplication) -> str:
    path = reverse(
        "users:registry_application_detail",
        kwargs={"pk": application.pk},
    )
    site_url = str(getattr(settings, "SITE_URL", "") or "").rstrip("/")
    if not site_url:
        return path
    return f"{site_url}{path}"


def _resolved_service_urls(
    application: RegistryApplication,
) -> tuple[str, str]:
    gateway_api = (application.gateway_api_base or "").strip()
    sync_url = (application.sync_service_url or "").strip()
    well_known = application.verified_well_known
    if isinstance(well_known, dict):
        if not gateway_api:
            value = well_known.get("gateway_api_base")
            if isinstance(value, str):
                gateway_api = value.strip()
        if not sync_url:
            value = well_known.get("sync_service_url")
            if isinstance(value, str):
                sync_url = value.strip()
    return gateway_api, sync_url


def build_pending_approval_staff_context(
    application: RegistryApplication,
) -> dict[str, Any]:
    """Template context for staff pending-approval email."""
    applicant_email = (
        application.contact_email
        or getattr(application.contact, "email", "")
        or "(unknown)"
    )
    proposed = (application.proposed_site_name or "").strip() or "(not set)"
    gateway_api, sync_url = _resolved_service_urls(application)
    return {
        "fqdn": application.fqdn,
        "display_name": application.display_name,
        "proposed_site_name": proposed,
        "applicant_email": applicant_email,
        "review_url": _application_detail_url(application),
        "gateway_api_base": gateway_api,
        "sync_service_url": sync_url,
        "site_url": settings.SITE_URL,
        "debug": settings.DEBUG,
    }


def build_pending_approval_staff_email_subject(
    application: RegistryApplication,
) -> str:
    return (
        f"Federation registry: domain verified — pending approval ({application.fqdn})"
    )


def build_pending_approval_staff_email(
    application: RegistryApplication,
) -> tuple[str, str]:
    """Plain-text body (used in tests and as alt content)."""
    ctx = build_pending_approval_staff_context(application)
    subject = build_pending_approval_staff_email_subject(application)
    lines = [
        (
            "A federation registry application passed domain verification "
            "and needs staff review."
        ),
        "",
        f"FQDN: {ctx['fqdn']}",
        f"Display name: {ctx['display_name']}",
        f"Proposed site id: {ctx['proposed_site_name']}",
        f"Applicant email: {ctx['applicant_email']}",
        f"Review: {ctx['review_url']}",
    ]
    if ctx["gateway_api_base"]:
        lines.append(f"Gateway API base: {ctx['gateway_api_base']}")
    if ctx["sync_service_url"]:
        lines.append(f"Sync service URL: {ctx['sync_service_url']}")
    lines.extend(
        [
            "",
            "Approve or reject the application in the gateway registry UI.",
        ]
    )
    return subject, "\n".join(lines)


def schedule_registry_pending_approval_staff_notify(
    application_pk: uuid.UUID | str,
) -> None:
    """Enqueue staff email after the current DB transaction commits."""
    pk = str(application_pk)

    def _enqueue() -> None:
        notify_registry_pending_approval_staff.delay(pk)

    transaction.on_commit(_enqueue)


@shared_task
def notify_registry_pending_approval_staff(application_id: str) -> int:
    """Send staff email; returns number of recipients mailed."""
    from sds_gateway.api_methods.tasks import send_email

    try:
        application = RegistryApplication.objects.select_related("contact").get(
            pk=application_id
        )
    except RegistryApplication.DoesNotExist:
        logger.warning(
            "registry staff notify: application {} not found",
            application_id,
        )
        return 0

    if application.status != RegistryApplicationStatus.PENDING_APPROVAL.value:
        logger.info(
            "registry staff notify: skip application {} status={}",
            application_id,
            application.status,
        )
        return 0

    recipients = registry_staff_notify_recipients()
    if not recipients:
        logger.warning("registry staff notify: no staff recipients configured")
        return 0

    context = build_pending_approval_staff_context(application)
    subject = build_pending_approval_staff_email_subject(application)
    send_email(
        subject=subject,
        recipient_list=recipients,
        plain_template=_PLAIN_TEMPLATE,
        html_template=_HTML_TEMPLATE,
        context=context,
    )
    logger.info(
        "registry staff notify: mailed {} recipients for {}",
        len(recipients),
        application.fqdn,
    )
    return len(recipients)
