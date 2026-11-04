"""Build, sign, and write registry manifest files on the flagship sync host."""

from __future__ import annotations

import fcntl
import json
from contextlib import suppress
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any

from sds_federation.models import FederationConfig  # noqa: TC001
from sds_federation.schemas.registry import REGISTRY_SCHEMA_VERSION
from sds_federation.schemas.registry import RegistrySite
from sds_federation.schemas.registry import SiteStatusEnum
from sds_federation.services.registry_sign import MANIFEST_FILENAME
from sds_federation.services.registry_sign import SERIAL_FILENAME
from sds_federation.services.registry_sign import SIGNATURE_FILENAME
from sds_federation.services.registry_sign import RegistrySignError
from sds_federation.services.registry_sign import atomic_write_bytes
from sds_federation.services.registry_sign import canonical_manifest_json_bytes
from sds_federation.services.registry_sign import encode_signature_for_well_known
from sds_federation.services.registry_sign import load_signing_private_key
from sds_federation.services.registry_sign import sign_manifest_payload
from sds_federation.services.well_known import default_gateway_api_base
from sds_federation.services.well_known import default_sync_service_url

_SITE_STATUS_ACTIVE = SiteStatusEnum.ACTIVE


def _format_manifest_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _flagship_site(config: FederationConfig) -> RegistrySite:
    site = config.site
    return RegistrySite(
        name=site.name,
        fqdn=site.fqdn,
        display_name=site.display_name,
        status=_SITE_STATUS_ACTIVE,
        gateway_api_base=default_gateway_api_base(config),
        sync_service_url=default_sync_service_url(config),
    )


def _normalized_fqdn(fqdn: str) -> str:
    return fqdn.strip().lower().rstrip(".")


def _site_to_manifest_entry(site: RegistrySite) -> dict[str, Any]:
    return {
        "name": site.name,
        "fqdn": site.fqdn,
        "display_name": site.display_name,
        "status": site.status.value,
        "gateway_api_base": str(site.gateway_api_base),
        "sync_service_url": str(site.sync_service_url),
        "ca_cert_file": site.ca_cert_file,
        "client_cert_fingerprints": list(site.client_cert_fingerprints),
    }


def build_manifest_sites(
    config: FederationConfig,
    extra_sites: list[RegistrySite],
) -> list[dict[str, Any]]:
    """Flagship first-class entry plus extras, keyed by FQDN (matches peer merge)."""
    flagship = _flagship_site(config)
    by_fqdn: dict[str, RegistrySite] = {_normalized_fqdn(flagship.fqdn): flagship}
    for site in extra_sites:
        key = _normalized_fqdn(site.fqdn)
        if key == _normalized_fqdn(flagship.fqdn) or site.name == flagship.name:
            continue  # flagship identity cannot be overridden by an extra site
        by_fqdn[key] = site
    names = [site.name for site in by_fqdn.values()]
    if len(names) != len(set(names)):
        msg = "registry sites must have unique names"
        raise ValueError(msg)
    return [
        _site_to_manifest_entry(site)
        for site in sorted(by_fqdn.values(), key=lambda s: s.name)
    ]


def build_manifest_dict(
    config: FederationConfig,
    *,
    serial: int,
    extra_sites: list[RegistrySite],
    issued_at: datetime | None = None,
    ttl_hours: int | None = None,
) -> dict[str, Any]:
    if serial < 0:
        msg = "manifest serial must be non-negative"
        raise ValueError(msg)
    issued = issued_at or datetime.now(UTC)
    hours = ttl_hours if ttl_hours is not None else config.registry.publish.ttl_hours
    expires = issued + timedelta(hours=hours)
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "serial": serial,
        "issued_at": _format_manifest_datetime(issued),
        "expires_at": _format_manifest_datetime(expires),
        "sites": build_manifest_sites(config, extra_sites),
    }


def _manifest_dir(config: FederationConfig) -> Path:
    raw = config.registry.publish.manifest_dir.strip()
    if not raw:
        msg = "registry publish manifest_dir is not configured"
        raise RegistrySignError(msg)
    return Path(raw)


def read_published_serial(config: FederationConfig) -> int:
    """Last published serial; -1 if nothing published.

    Falls back to the serial inside ``sites.json`` when the ``serial`` file is
    missing or corrupt, so a damaged file can never roll the serial back.
    """
    storage_dir = _manifest_dir(config)
    serial_path = storage_dir / SERIAL_FILENAME
    if serial_path.is_file():
        with suppress(ValueError, OSError):
            return int(serial_path.read_text(encoding="utf-8").strip())
    manifest_path = storage_dir / MANIFEST_FILENAME
    if manifest_path.is_file():
        with suppress(ValueError, OSError, TypeError):
            return int(json.loads(manifest_path.read_bytes())["serial"])
    return -1


def _write_manifest_files(
    storage_dir: Path,
    payload: bytes,
    signature_b64: bytes,
    serial: int,
) -> None:
    storage_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(storage_dir / MANIFEST_FILENAME, payload)
    atomic_write_bytes(storage_dir / SIGNATURE_FILENAME, signature_b64)
    atomic_write_bytes(storage_dir / SERIAL_FILENAME, str(serial).encode("utf-8"))


def read_published_manifest_bytes(config: FederationConfig) -> bytes | None:
    path = _manifest_dir(config) / MANIFEST_FILENAME
    if not path.is_file():
        return None
    return path.read_bytes()


def read_published_signature_bytes(config: FederationConfig) -> bytes | None:
    path = _manifest_dir(config) / SIGNATURE_FILENAME
    if not path.is_file():
        return None
    return path.read_bytes()


def publish_manifest(
    config: FederationConfig,
    sites: list[RegistrySite],
    min_serial: int | None,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    publish = config.registry.publish
    key_path = publish.signing_key_path.strip()
    if not key_path:
        msg = "registry signing key path is not configured"
        raise RegistrySignError(msg)

    storage_dir = _manifest_dir(config)
    if dry_run:
        # No directory/lock side effects: read-only preview of the next manifest.
        result, _, _ = _build_and_sign(config, sites, min_serial, key_path)
        return {**result, "dry_run": True}

    storage_dir.mkdir(parents=True, exist_ok=True)
    with (storage_dir / ".lock").open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        result, payload, signature_b64 = _build_and_sign(
            config, sites, min_serial, key_path
        )
        _write_manifest_files(storage_dir, payload, signature_b64, result["serial"])
        return result


def _build_and_sign(
    config: FederationConfig,
    sites: list[RegistrySite],
    min_serial: int | None,
    key_path: str,
) -> tuple[dict[str, Any], bytes, bytes]:
    floor = (min_serial or 0) - 1
    serial = max(read_published_serial(config), floor) + 1
    manifest = build_manifest_dict(config, serial=serial, extra_sites=sites)
    payload = canonical_manifest_json_bytes(manifest)
    signature = sign_manifest_payload(payload, load_signing_private_key(key_path))
    result = {
        "serial": serial,
        "issued_at": manifest["issued_at"],
        "expires_at": manifest["expires_at"],
        "site_names": [str(s["name"]) for s in manifest["sites"]],
        "dry_run": False,
    }
    return result, payload, encode_signature_for_well_known(signature)
