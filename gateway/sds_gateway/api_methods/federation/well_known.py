"""Site self-description at /.well-known/sds-federation.json (RFC 8615)."""

from __future__ import annotations

from typing import Any

from django.conf import settings

SDS_FEDERATION_WELL_KNOWN_SCHEMA_VERSION = 1
WELL_KNOWN_SDS_FEDERATION_PATH = "/.well-known/sds-federation.json"

_LOCAL_GATEWAY_HOST = "sds-gateway-local-app"
_LOCAL_SYNC_HOST = "sds-federation-local-sync"


def _setting_str(name: str, default: str = "") -> str:
    return str(getattr(settings, name, default) or "").strip()


def _is_local_federation_lab() -> bool:
    """Lab defaults match federation.toml Docker DNS (not public HTTPS)."""
    return getattr(settings, "ADMIN_CONSOLE_ENV", "") == "local"


def default_public_gateway_api_base(fqdn: str) -> str:
    api_version = _setting_str("API_VERSION", "v1")
    return f"https://{fqdn}/api/{api_version}"


def default_public_sync_service_url(fqdn: str) -> str:
    return f"https://{fqdn}/sync/"


def default_local_gateway_api_base() -> str:
    api_version = _setting_str("API_VERSION", "v1")
    return f"http://{_LOCAL_GATEWAY_HOST}:8000/api/{api_version}"


def default_local_sync_service_url() -> str:
    return f"http://{_LOCAL_SYNC_HOST}:8000/sync"


def resolve_gateway_api_base(fqdn: str) -> str:
    explicit = _setting_str("FEDERATION_GATEWAY_API_BASE")
    if explicit:
        return explicit
    if _is_local_federation_lab():
        return default_local_gateway_api_base()
    return default_public_gateway_api_base(fqdn) if fqdn else ""


def resolve_sync_service_url(fqdn: str) -> str:
    explicit = _setting_str("FEDERATION_SYNC_SERVICE_URL")
    if explicit:
        return explicit
    if _is_local_federation_lab():
        return default_local_sync_service_url()
    return default_public_sync_service_url(fqdn) if fqdn else ""


def default_local_well_known_fetch_base() -> str:
    """Docker DNS for registry verify in the local lab (same compose stack)."""
    return f"http://{_LOCAL_GATEWAY_HOST}:8000"


def resolve_well_known_fetch_url(fqdn: str) -> str:
    """URL mothership verify uses to fetch an applicant's well-known JSON.

    Production/staging: always ``https://{fqdn}/.well-known/...``.

    Local lab: when the application FQDN matches ``SDS_SITE_FQDN``, fetch over HTTP
    from the gateway container (no Traefik/TLS required). Optional
    ``FEDERATION_REGISTRY_VERIFY_FETCH_BASE`` overrides that base URL.
    """
    normalized = fqdn.strip().lower()
    if _is_local_federation_lab():
        site_fqdn = _setting_str("SDS_SITE_FQDN").lower()
        if site_fqdn and normalized == site_fqdn:
            base = (
                _setting_str("FEDERATION_REGISTRY_VERIFY_FETCH_BASE")
                or default_local_well_known_fetch_base()
            )
            return f"{base.rstrip('/')}{WELL_KNOWN_SDS_FEDERATION_PATH}"
    if not normalized:
        return f"https://{normalized}{WELL_KNOWN_SDS_FEDERATION_PATH}"
    return f"https://{normalized}{WELL_KNOWN_SDS_FEDERATION_PATH}"


def build_sds_federation_document(
    *,
    registry_challenge: str | None = None,
) -> dict[str, Any]:
    """Unsigned federation identity document for this gateway host."""
    fqdn = _setting_str("SDS_SITE_FQDN")
    name = _setting_str("FEDERATION_SITE_NAME")
    display_name = _setting_str("SDS_SITE_DISPLAY_NAME") or name

    doc: dict[str, Any] = {
        "schema_version": SDS_FEDERATION_WELL_KNOWN_SCHEMA_VERSION,
        "name": name,
        "fqdn": fqdn,
        "display_name": display_name,
        "gateway_api_base": resolve_gateway_api_base(fqdn),
        "sync_service_url": resolve_sync_service_url(fqdn),
    }

    challenge = (
        registry_challenge or _setting_str("FEDERATION_REGISTRY_CHALLENGE_TOKEN")
    ).strip()
    if challenge:
        doc["registry_challenge"] = challenge

    registry_url = _setting_str("FEDERATION_REGISTRY_WELL_KNOWN_URL")
    if registry_url:
        doc["registry_url"] = registry_url

    registry_fingerprint = _setting_str("FEDERATION_REGISTRY_PUBKEY_FINGERPRINT")
    if registry_fingerprint:
        doc["registry_pubkey_fingerprint"] = registry_fingerprint

    contact = _setting_str("SDS_FEDERATION_WELL_KNOWN_CONTACT")
    if contact:
        doc["contact"] = contact

    return doc


def well_known_document_ready(doc: dict[str, Any]) -> bool:
    """Minimum fields required for discovery and domain verification."""
    for key in (
        "schema_version",
        "name",
        "fqdn",
        "display_name",
        "gateway_api_base",
        "sync_service_url",
    ):
        value = doc.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            return False
    return True
