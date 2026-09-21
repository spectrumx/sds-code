from __future__ import annotations

import base64
import json
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from loguru import logger

from sds_federation.models import PeerInfo
from sds_federation.schemas.registry import REGISTRY_SCHEMA_VERSION
from sds_federation.schemas.registry import RegistryManifest
from sds_federation.schemas.registry import RegistrySite

if TYPE_CHECKING:
    from sds_federation.models import FederationConfig
    from sds_federation.models import RegistryPolicy

_MANIFEST_NAME = "sites.json"
_SIGNATURE_NAME = "sites.json.sig"
_SERIAL_NAME = "serial"


class RegistryTrustError(Exception):
    """Manifest failed signature, freshness, or rollback checks."""


def _public_key(policy: RegistryPolicy) -> Ed25519PublicKey:
    key = load_pem_public_key(Path(policy.public_key_path).read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        msg = f"registry key at {policy.public_key_path} is not Ed25519"
        raise RegistryTrustError(msg)
    return key


def _verify(policy: RegistryPolicy, payload: bytes, signature: bytes) -> None:
    try:
        _public_key(policy).verify(signature, payload)
    except InvalidSignature as exc:
        raise RegistryTrustError("registry signature verification failed") from exc


def _last_serial(policy: RegistryPolicy) -> int:
    path = Path(policy.cache_dir) / _SERIAL_NAME
    if not path.is_file():
        return -1
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return -1


def _accept(
    policy: RegistryPolicy,
    payload: bytes,
    signature: bytes,
    *,
    now: datetime | None = None,
) -> RegistryManifest:
    """Verify signature, schema, freshness, and serial monotonicity."""
    _verify(policy, payload, signature)
    manifest = RegistryManifest.model_validate(json.loads(payload))
    if manifest.schema_version != REGISTRY_SCHEMA_VERSION:
        msg = (
            f"registry schema_version {manifest.schema_version} != "
            f"{REGISTRY_SCHEMA_VERSION}"
        )
        raise RegistryTrustError(msg)
    if manifest.is_expired(now=now):
        msg = f"registry manifest expired at {manifest.expires_at.isoformat()}"
        raise RegistryTrustError(msg)
    last = _last_serial(policy)
    if manifest.serial < last:
        msg = f"registry serial {manifest.serial} older than accepted {last}"
        raise RegistryTrustError(msg)
    return manifest


def _cache(policy: RegistryPolicy, payload: bytes, signature: bytes, serial: int) -> None:
    cache_dir = Path(policy.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / _MANIFEST_NAME).write_bytes(payload)
    (cache_dir / _SIGNATURE_NAME).write_bytes(signature)
    (cache_dir / _SERIAL_NAME).write_text(str(serial), encoding="utf-8")


def load_cached_manifest(policy: RegistryPolicy) -> RegistryManifest | None:
    """Last-known-good manifest, still subject to signature and expiry checks."""
    cache_dir = Path(policy.cache_dir)
    payload_path = cache_dir / _MANIFEST_NAME
    signature_path = cache_dir / _SIGNATURE_NAME
    if not (payload_path.is_file() and signature_path.is_file()):
        return None
    try:
        return _accept(
            policy,
            payload_path.read_bytes(),
            base64.b64decode(signature_path.read_bytes(), validate=True),
        )
    except (RegistryTrustError, ValueError) as exc:
        logger.error("cached registry manifest rejected: {}", exc)
        return None


async def fetch_manifest(
    http: httpx.AsyncClient,
    policy: RegistryPolicy,
) -> RegistryManifest:
    base = str(policy.url).rstrip("/")
    payload = (await http.get(f"{base}/{_MANIFEST_NAME}")).raise_for_status().content
    raw_sig = (await http.get(f"{base}/{_SIGNATURE_NAME}")).raise_for_status().content
    signature = base64.b64decode(raw_sig.strip(), validate=True)
    manifest = _accept(policy, payload, signature)
    _cache(policy, payload, signature, manifest.serial)
    return manifest