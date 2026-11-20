"""Optional applicant /sync/health probes before registry manifest publish."""

from __future__ import annotations

from collections.abc import Iterable

import requests
from loguru import logger

from sds_gateway.api_methods.models import RegistryApplication

_DEFAULT_TIMEOUT_SECS = 12.0


def sync_health_check_url(fqdn: str, sync_service_url: str) -> str:
    fqdn = fqdn.strip().lower()
    base = sync_service_url.strip().rstrip("/")
    if not base:
        base = f"https://{fqdn}/sync"
    if base.endswith("/health"):
        return base
    return f"{base}/health"


def _resolve_sync_service_url(application: RegistryApplication) -> str:
    sync_url = (application.sync_service_url or "").strip()
    well_known = application.verified_well_known
    if not sync_url and isinstance(well_known, dict):
        value = well_known.get("sync_service_url")
        if isinstance(value, str) and value.strip():
            sync_url = value.strip()
    return sync_url


def applicant_sync_health_ok(url: str, *, timeout: float = _DEFAULT_TIMEOUT_SECS) -> bool:
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code != 200:
            return False
        data = response.json()
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.debug("registry publish health: {} failed: {}", url, exc)
        return False
    return isinstance(data, dict) and data.get("status") == "ok"


def publish_health_warnings_for_applications(
    applications: Iterable[RegistryApplication],
    *,
    enabled: bool,
) -> list[str]:
    if not enabled:
        return []
    warnings: list[str] = []
    for application in applications:
        fqdn = (application.fqdn or "").strip()
        if not fqdn:
            continue
        health_url = sync_health_check_url(fqdn, _resolve_sync_service_url(application))
        if applicant_sync_health_ok(health_url):
            continue
        label = (application.site_name or fqdn).strip()
        warnings.append(f"{label}: /sync/health check failed ({health_url})")
    return warnings