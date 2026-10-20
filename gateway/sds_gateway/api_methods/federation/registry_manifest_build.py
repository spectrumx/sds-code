"""Build RegistryManifest-shaped dicts from flagship settings and approved applications."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone

from sds_gateway.api_methods.federation.registry_manifest_sign import (
    REGISTRY_MANIFEST_SCHEMA_VERSION,
)
from sds_gateway.api_methods.federation.well_known import resolve_gateway_api_base
from sds_gateway.api_methods.federation.well_known import resolve_sync_service_url
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus

_MANIFEST_MEMBER_STATUSES = (
    RegistryApplicationStatus.APPROVED.value,
    RegistryApplicationStatus.PUBLISHED.value,
)
_SITE_STATUS_ACTIVE = "active"


def format_manifest_datetime(dt: datetime) -> str:
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _api_version() -> str:
    return str(getattr(settings, "API_VERSION", "v1") or "v1").strip()


def _default_gateway_api_base(fqdn: str) -> str:
    return f"https://{fqdn}/api/{_api_version()}"


def _default_sync_service_url(fqdn: str) -> str:
    return f"https://{fqdn}/sync"


def build_flagship_site_entry() -> dict[str, Any]:
    fqdn = str(getattr(settings, "SDS_SITE_FQDN", "") or "").strip()
    name = str(getattr(settings, "FEDERATION_SITE_NAME", "") or "").strip()
    display_name = (
        str(getattr(settings, "SDS_SITE_DISPLAY_NAME", "") or "").strip() or name
    )
    if not fqdn or not name:
        msg = "SDS_SITE_FQDN and FEDERATION_SITE_NAME must be set to build the manifest"
        raise ValueError(msg)
    return {
        "name": name,
        "fqdn": fqdn,
        "display_name": display_name,
        "status": _SITE_STATUS_ACTIVE,
        "gateway_api_base": resolve_gateway_api_base(fqdn),
        "sync_service_url": resolve_sync_service_url(fqdn),
        "ca_cert_file": "",
        "client_cert_fingerprints": [],
    }


def _urls_for_application(application: RegistryApplication) -> tuple[str, str]:
    gateway = (application.gateway_api_base or "").strip()
    sync_url = (application.sync_service_url or "").strip()
    well_known = application.verified_well_known or {}
    if not gateway:
        gateway = str(well_known.get("gateway_api_base") or "").strip()
    if not sync_url:
        sync_url = str(well_known.get("sync_service_url") or "").strip()
    fqdn = application.fqdn.strip()
    if not gateway:
        gateway = _default_gateway_api_base(fqdn)
    if not sync_url:
        sync_url = _default_sync_service_url(fqdn)
    return gateway, sync_url


def site_entry_from_application(application: RegistryApplication) -> dict[str, Any]:
    site_name = (application.site_name or "").strip()
    if not site_name:
        msg = f"application {application.pk} has no site_name"
        raise ValueError(msg)
    gateway, sync_url = _urls_for_application(application)
    fingerprints = application.client_cert_fingerprints or []
    if not isinstance(fingerprints, list):
        fingerprints = []
    return {
        "name": site_name,
        "fqdn": application.fqdn.strip(),
        "display_name": application.display_name.strip(),
        "status": _SITE_STATUS_ACTIVE,
        "gateway_api_base": gateway,
        "sync_service_url": sync_url,
        "ca_cert_file": (application.ca_cert_file or "").strip(),
        "client_cert_fingerprints": [str(f) for f in fingerprints],
    }


def build_manifest_sites() -> list[dict[str, Any]]:
    """All active manifest members: flagship plus approved/published applications."""
    flagship = build_flagship_site_entry()
    flagship_fqdn = flagship["fqdn"].strip().lower()
    by_name: dict[str, dict[str, Any]] = {flagship["name"]: flagship}

    applications = (
        RegistryApplication.objects.filter(status__in=_MANIFEST_MEMBER_STATUSES)
        .exclude(site_name="")
        .order_by("site_name")
    )
    for application in applications:
        entry = site_entry_from_application(application)
        if entry["fqdn"].strip().lower() == flagship_fqdn:
            continue
        by_name[entry["name"]] = entry

    return [by_name[key] for key in sorted(by_name)]


def build_manifest_dict(
    *,
    serial: int,
    issued_at: datetime | None = None,
    ttl_hours: int | None = None,
) -> dict[str, Any]:
    if serial < 0:
        msg = "manifest serial must be non-negative"
        raise ValueError(msg)
    issued = issued_at or timezone.now()
    hours = ttl_hours
    if hours is None:
        hours = int(getattr(settings, "FEDERATION_REGISTRY_MANIFEST_TTL_HOURS", 168))
    expires = issued + timedelta(hours=hours)
    return {
        "schema_version": REGISTRY_MANIFEST_SCHEMA_VERSION,
        "serial": serial,
        "issued_at": format_manifest_datetime(issued),
        "expires_at": format_manifest_datetime(expires),
        "sites": build_manifest_sites(),
    }
