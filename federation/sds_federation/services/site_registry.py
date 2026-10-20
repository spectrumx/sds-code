from __future__ import annotations

import asyncio
import base64
import json
from contextlib import suppress
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
from sds_federation.services.bootstrap import bootstrap_peer_sync_list
from sds_federation.services.bootstrap import push_site_hello_to_peer

if TYPE_CHECKING:
    from datetime import datetime

    from sds_federation.models import FederationConfig
    from sds_federation.models import RegistryPolicy
    from sds_federation.services.fed_index import FederatedAssetIndexer

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


def _cache(
    policy: RegistryPolicy, payload: bytes, signature: bytes, serial: int
) -> None:
    cache_dir = Path(policy.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / _MANIFEST_NAME).write_bytes(payload)
    (cache_dir / _SIGNATURE_NAME).write_bytes(base64.b64encode(signature))
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


def _peer_from_site(site: RegistrySite, policy: RegistryPolicy) -> PeerInfo:
    ca_path = ""
    if site.ca_cert_file:
        # Basename only: the manifest must not be able to select host paths.
        candidate = Path(policy.certs_dir) / Path(site.ca_cert_file).name
        if candidate.is_file():
            ca_path = str(candidate)
        else:
            logger.warning("registry CA for {} not found at {}", site.name, candidate)
    return PeerInfo(
        name=site.name,
        fqdn=site.fqdn,
        display_name=site.display_name,
        gateway_api_base=site.gateway_api_base,
        sync_service_url=site.sync_service_url,
        ca_cert_path=ca_path,
    )


def merge_peers(
    config: FederationConfig,
    manifest: RegistryManifest,
) -> list[PeerInfo]:
    """Static peers pinned by the operator, plus active registry sites."""
    policy = config.registry
    denied = set(policy.deny)
    merged = {peer.fqdn: peer for peer in config.peers}
    for site in manifest.active_sites():
        if site.fqdn == config.site.fqdn or site.name == config.site.name:
            continue
        if site.fqdn in denied or site.name in denied:
            logger.info("registry site {} skipped by local deny list", site.fqdn)
            continue
        merged.setdefault(site.fqdn, _peer_from_site(site, policy))
    return list(merged.values())


async def resolve_peers(
    http: httpx.AsyncClient,
    config: FederationConfig,
) -> list[PeerInfo]:
    """Peer set for this cycle: registry when trusted, static config otherwise."""
    policy = config.registry
    if not policy.url or not policy.public_key_path:
        return list(config.peers)
    try:
        manifest = await fetch_manifest(http, policy)
    except (httpx.HTTPError, RegistryTrustError, ValueError) as exc:
        logger.error("registry fetch failed: {}", exc)
        manifest = load_cached_manifest(policy)
        if manifest is None:
            if policy.required:
                msg = "no trusted registry manifest and registry.required=true"
                raise RegistryTrustError(msg) from exc
            logger.warning("continuing with static federation.toml peers only")
            return list(config.peers)
        logger.info("using cached registry manifest serial {}", manifest.serial)
    return merge_peers(config, manifest)


async def apply_peers(
    config: FederationConfig, peers: list[PeerInfo]
) -> list[PeerInfo]:
    """Replace the peer list in place so every config holder sees the update."""
    known = {peer.fqdn for peer in config.peers}
    config.peers[:] = peers
    return [peer for peer in peers if peer.fqdn not in known]


async def run_registry_refresh(
    http: httpx.AsyncClient,
    config: FederationConfig,
    indexer: FederatedAssetIndexer,
    stop: asyncio.Event,
) -> None:
    policy = config.registry
    if not policy.url:
        return
    while not stop.is_set():
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=policy.refresh_secs)
        if stop.is_set():
            return
        try:
            peers = await resolve_peers(http, config)
        except RegistryTrustError as exc:
            logger.error("registry refresh rejected: {}", exc)
            continue
        for peer in await apply_peers(config, peers):
            logger.info("registry added peer {} ({})", peer.name, peer.fqdn)
            await bootstrap_peer_sync_list(http, peer, indexer)
            with suppress(httpx.HTTPError):
                await push_site_hello_to_peer(http, peer, config)
