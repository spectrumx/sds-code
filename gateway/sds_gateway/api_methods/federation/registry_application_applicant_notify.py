"""Applicant notification when a registry application is published in the manifest."""

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

_PLAIN_TEMPLATE = "emails/registry_application_published.txt"
_HTML_TEMPLATE = "emails/registry_application_published.html"


def _application_detail_url(application: RegistryApplication) -> str:
    path = reverse(
        "users:registry_application_detail",
        kwargs={"pk": application.pk},
    )
    site_url = str(getattr(settings, "SITE_URL", "") or "").rstrip("/")
    if not site_url:
        return path
    return f"{site_url}{path}"


def registry_applicant_recipient(application: RegistryApplication) -> str:
    email = (application.contact_email or "").strip()
    if email:
        return email
    contact = getattr(application, "contact", None)
    if contact is not None:
        return str(getattr(contact, "email", "") or "").strip()
    return ""


def build_published_applicant_context(
    application: RegistryApplication,
) -> dict[str, Any]:
    site_name = (application.site_name or "").strip() or "(not set)"
    return {
        "fqdn": application.fqdn,
        "display_name": application.display_name,
        "site_name": site_name,
        "manifest_serial": application.published_manifest_serial,
        "application_url": _application_detail_url(application),
        "site_url": settings.SITE_URL,
        "debug": settings.DEBUG,
    }


def build_published_applicant_email_subject(
    application: RegistryApplication,
) -> str:
    return (
        f"Federation registry: your site is published "
        f"({application.fqdn or application.site_name})"
    )


def schedule_registry_application_applicant_notify(
    application_pk: uuid.UUID | str,
) -> None:
    """Enqueue applicant email after the current DB transaction commits."""
    pk = str(application_pk)

    def _enqueue() -> None:
        notify_registry_application_published.delay(pk)

    transaction.on_commit(_enqueue)


@shared_task
def notify_registry_application_published(application_id: str) -> int:
    """Email the applicant; returns 1 if sent, else 0."""
    from sds_gateway.api_methods.tasks import send_email

    try:
        application = RegistryApplication.objects.select_related("contact").get(
            pk=application_id
        )
    except RegistryApplication.DoesNotExist:
        logger.warning(
            "registry applicant notify: application {} not found",
            application_id,
        )
        return 0

    if application.status != RegistryApplicationStatus.PUBLISHED.value:
        logger.info(
            "registry applicant notify: skip application {} status={}",
            application_id,
            application.status,
        )
        return 0

    recipient = registry_applicant_recipient(application)
    if not recipient:
        logger.warning(
            "registry applicant notify: no email for application {}",
            application_id,
        )
        return 0

    context = build_published_applicant_context(application)
    subject = build_published_applicant_email_subject(application)
    send_email(
        subject=subject,
        recipient_list=[recipient],
        plain_template=_PLAIN_TEMPLATE,
        html_template=_HTML_TEMPLATE,
        context=context,
    )
    logger.info(
        "registry applicant notify: mailed {} for {}",
        recipient,
        application.fqdn,
    )
    return 1