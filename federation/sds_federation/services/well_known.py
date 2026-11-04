"""Site self-description at /.well-known/sds-federation.json."""

from __future__ import annotations

import os
from typing import Any

from sds_federation.models import FederationConfig

SDS_FEDERATION_WELL_KNOWN_SCHEMA_VERSION = 1
WELL_KNOWN_SDS_FEDERATION_PATH = "/.well-known/sds-federation.json"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _default_gateway_api_base(config: FederationConfig) -> str:
    if config.site.gateway_api_base is not None:
        return str(config.site.gateway_api_base)
    explicit = _env("FEDERATION_GATEWAY_API_BASE")
    if explicit:
        return explicit.rstrip("/")
    fqdn = config.site.fqdn.strip()
    api_version = _env("API_VERSION", "v1")
    return f"https://{fqdn}/api/{api_version}"


def _default_sync_service_url(config: FederationConfig) -> str:
    if config.site.sync_service_url is not None:
        return str(config.site.sync_service_url).rstrip("/")
    explicit = _env("FEDERATION_SYNC_SERVICE_URL")
    if explicit:
        return explicit.rstrip("/")
    fqdn = config.site.fqdn.strip()
    return f"https://{fqdn}/sync"


def build_site_document(config: FederationConfig) -> dict[str, Any]:
    site = config.site
    doc: dict[str, Any] = {
        "schema_version": SDS_FEDERATION_WELL_KNOWN_SCHEMA_VERSION,
        "name": site.name,
        "fqdn": site.fqdn,
        "display_name": site.display_name,
        "gateway_api_base": _default_gateway_api_base(config),
        "sync_service_url": _default_sync_service_url(config),
    }
    challenge = _env("FEDERATION_REGISTRY_CHALLENGE_TOKEN")
    if challenge:
        doc["registry_challenge"] = challenge
    registry_url = _env("FEDERATION_REGISTRY_WELL_KNOWN_URL")
    if registry_url:
        doc["registry_url"] = registry_url
    fingerprint = _env("FEDERATION_REGISTRY_PUBKEY_FINGERPRINT")
    if fingerprint:
        doc["registry_pubkey_fingerprint"] = fingerprint
    contact = _env("SDS_FEDERATION_WELL_KNOWN_CONTACT")
    if contact:
        doc["contact"] = contact
    return doc


def document_ready(doc: dict[str, Any]) -> bool:
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
