"""Build signed registry manifest site entries from RegistryApplication rows."""

from __future__ import annotations

from typing import Any

from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus

_PUBLISHABLE_STATUSES = (
    RegistryApplicationStatus.APPROVED.value,
    RegistryApplicationStatus.PUBLISHED.value,
)


class ManifestBuildError(Exception):
    """Site list cannot be built for sync publish."""


def _default_gateway_api_base(fqdn: str) -> str:
    return f"https://{fqdn.strip().lower()}/api/v1"


def _default_sync_service_url(fqdn: str) -> str:
    return f"https://{fqdn.strip().lower()}/sync"


def _resolve_service_urls(application: RegistryApplication) -> tuple[str, str]:
    gateway = (application.gateway_api_base or "").strip()
    sync_url = (application.sync_service_url or "").strip()
    well_known = application.verified_well_known
    if isinstance(well_known, dict):
        if not gateway:
            value = well_known.get("gateway_api_base")
            if isinstance(value, str) and value.strip():
                gateway = value.strip()
        if not sync_url:
            value = well_known.get("sync_service_url")
            if isinstance(value, str) and value.strip():
                sync_url = value.strip()
    fqdn = application.fqdn.strip()
    if not gateway:
        gateway = _default_gateway_api_base(fqdn)
    if not sync_url:
        sync_url = _default_sync_service_url(fqdn)
    return gateway, sync_url


def site_entry_from_application(application: RegistryApplication) -> dict[str, Any]:
    """JSON object matching federation sync ``RegistrySite`` (status omitted)."""
    site_name = (application.site_name or "").strip()
    if not site_name:
        msg = f"{application.fqdn}: site id is not set (approve the application first)."
        raise ManifestBuildError(msg)
    fqdn = (application.fqdn or "").strip()
    if not fqdn:
        msg = "Registry application is missing FQDN."
        raise ManifestBuildError(msg)
    display_name = (application.display_name or "").strip()
    if not display_name:
        msg = f"{site_name}: display name is required."
        raise ManifestBuildError(msg)

    gateway_api_base, sync_service_url = _resolve_service_urls(application)
    fingerprints = application.client_cert_fingerprints
    if fingerprints is None:
        fingerprints = []
    elif not isinstance(fingerprints, list):
        msg = f"{site_name}: client_cert_fingerprints must be a list."
        raise ManifestBuildError(msg)

    return {
        "name": site_name,
        "fqdn": fqdn,
        "display_name": display_name,
        "gateway_api_base": gateway_api_base,
        "sync_service_url": sync_service_url,
        "ca_cert_file": (application.ca_cert_file or "").strip(),
        "client_cert_fingerprints": [str(item) for item in fingerprints],
    }


def build_manifest_site_list() -> list[dict[str, Any]]:
    """All approved and published applications for the next manifest snapshot."""
    applications = list(
        RegistryApplication.objects.filter(
            status__in=_PUBLISHABLE_STATUSES,
        )
        .exclude(site_name="")
        .order_by("site_name")
    )
    entries: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    seen_fqdns: set[str] = set()
    for application in applications:
        entry = site_entry_from_application(application)
        name = entry["name"]
        fqdn = entry["fqdn"].strip().lower()
        if name in seen_names:
            msg = f"Duplicate site id '{name}' in registry applications."
            raise ManifestBuildError(msg)
        if fqdn in seen_fqdns:
            msg = f"Duplicate FQDN '{fqdn}' in registry applications."
            raise ManifestBuildError(msg)
        seen_names.add(name)
        seen_fqdns.add(fqdn)
        entries.append(entry)
    return entries


def manifest_min_serial() -> int:
    """Lower bound for sync manifest serial from gateway DB."""
    from django.db.models import Max

    agg = RegistryApplication.objects.aggregate(
        max_serial=Max("published_manifest_serial")
    )
    max_serial = agg["max_serial"]
    if max_serial is None:
        return 0
    return int(max_serial) + 1


def manifest_peer_site_names(sites: list[dict[str, Any]]) -> list[str]:
    return [str(site["name"]) for site in sites]
