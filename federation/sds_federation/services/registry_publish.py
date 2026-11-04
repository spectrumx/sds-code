"""Build, sign, and write registry manifest files on the flagship sync host."""

from __future__ import annotations

import fcntl
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any

from sds_federation.models import FederationConfig
from sds_federation.schemas.registry import REGISTRY_SCHEMA_VERSION
from sds_federation.schemas.registry import RegistrySite
from sds_federation.schemas.registry import SiteStatusEnum
from sds_federation.services.registry_sign import MANIFEST_FILENAME
from sds_federation.services.registry_sign import SERIAL_FILENAME
from sds_federation.services.registry_sign import SIGNATURE_FILENAME
from sds_federation.services.registry_sign import RegistrySignError
from sds_federation.services.registry_sign import canonical_manifest_json_bytes
from sds_federation.services.registry_sign import encode_signature_for_well_known
from sds_federation.services.registry_sign import load_signing_private_key
from sds_federation.services.registry_sign import sign_manifest_payload
from sds_federation.services.well_known import _default_gateway_api_base
from sds_federation.services.well_known import _default_sync_service_url

_SITE_STATUS_ACTIVE = SiteStatusEnum.ACTIVE


def _format_manifest_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _flagship_site_entry(config: FederationConfig) -> dict[str, Any]:
    site = config.site
    return {
        "name": site.name,
        "fqdn": site.fqdn,
        "display_name": site.display_name,
        "status": _SITE_STATUS_ACTIVE.value,
        "gateway_api_base": _default_gateway_api_base(config),
        "sync_service_url": _default_sync_service_url(config),
        "ca_cert_file": "",
        "client_cert_fingerprints": [],
    }


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
    flagship = _flagship_site_entry(config)
    flagship_fqdn = flagship["fqdn"].strip().lower()
    by_name: dict[str, dict[str, Any]] = {flagship["name"]: flagship}
    for site in extra_sites:
        entry = _site_to_manifest_entry(site)
        if entry["fqdn"].strip().lower() == flagship_fqdn:
            continue
        by_name[entry["name"]] = entry
    return [by_name[key] for key in sorted(by_name)]


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
    serial_path = _manifest_dir(config) / SERIAL_FILENAME
    if not serial_path.is_file():
        return -1
    try:
        return int(serial_path.read_text(encoding="utf-8").strip())
    except ValueError:
        return -1


def _write_manifest_files(
    storage_dir: Path,
    payload: bytes,
    signature_b64: bytes,
    serial: int,
) -> None:
    storage_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = storage_dir / MANIFEST_FILENAME
    sig_path = storage_dir / SIGNATURE_FILENAME
    serial_path = storage_dir / SERIAL_FILENAME

    tmp_manifest = manifest_path.with_suffix(".json.tmp")
    tmp_sig = sig_path.with_suffix(".sig.tmp")
    tmp_manifest.write_bytes(payload)
    tmp_sig.write_bytes(signature_b64)
    tmp_manifest.replace(manifest_path)
    tmp_sig.replace(sig_path)
    serial_path.write_text(str(serial), encoding="utf-8")


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
    dry_run: bool,
) -> dict[str, Any]:
    publish = config.registry.publish
    key_path = publish.signing_key_path.strip()
    if not key_path:
        msg = "registry signing key path is not configured"
        raise RegistrySignError(msg)

    storage_dir = _manifest_dir(config)
    lock_path = storage_dir / ".lock"
    storage_dir.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        file_serial = read_published_serial(config)
        floor = (min_serial or 0) - 1
        serial = max(file_serial, floor) + 1
        manifest = build_manifest_dict(config, serial=serial, extra_sites=sites)
        payload = canonical_manifest_json_bytes(manifest)
        private_key = load_signing_private_key(key_path)
        signature = sign_manifest_payload(payload, private_key)
        signature_b64 = encode_signature_for_well_known(signature)
        site_names = [str(s["name"]) for s in manifest["sites"]]
        if not dry_run:
            _write_manifest_files(storage_dir, payload, signature_b64, serial)
        return {
            "serial": serial,
            "issued_at": manifest["issued_at"],
            "expires_at": manifest["expires_at"],
            "site_names": site_names,
            "dry_run": dry_run,
        }
