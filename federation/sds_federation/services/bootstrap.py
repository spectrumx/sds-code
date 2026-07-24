"""Bootstrap federated metadata from gateway export APIs and register with peers."""

from __future__ import annotations

import os
from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING

import httpx
from loguru import logger

from sds_federation.models import FederationConfig
from sds_federation.models import PeerInfo
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import FederatedCaptureDoc
from sds_federation.schemas.webhooks import FederatedDatasetDoc
from sds_federation.schemas.webhooks import SiteHelloWebhook
from sds_federation.schemas.webhooks import asset_doc_class
from sds_federation.services.peer_sync import peer_webhook_url

if TYPE_CHECKING:
    from sds_federation.services.fed_index import FederatedAssetIndexer

SITE_HELLO_PATH = "/webhook/site-hello"
_MINT_PATH = "/users/get-federation-sync-api-key/"


def _export_list_url(peer: PeerInfo, asset_type: AssetTypeEnum) -> str:
    base = str(peer.gateway_api_base).rstrip("/")
    return f"{base}{asset_type.export_path}"


def _gateway_origin(gateway_api_base: str) -> str:
    """Strip ``/api/v1`` (or ``/api/<version>``) so non-API routes resolve."""
    base = str(gateway_api_base).rstrip("/")
    if base.endswith("/api/v1"):
        return base[: -len("/api/v1")]
    marker = "/api/"
    if marker in base:
        return base.rsplit(marker, 1)[0]
    return base


def mint_api_key_url(gateway_api_base: str) -> str:
    """Gateway mint lives at ``/users/...``, not under ``/api/v1``."""
    return f"{_gateway_origin(gateway_api_base)}{_MINT_PATH}"


def _gateway_auth_headers(api_key: str) -> dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Api-Key: {api_key}"}


def _resolve_gateway_api_key(peer: PeerInfo) -> str:
    if peer.gateway_export_api_key:
        return peer.gateway_export_api_key
    return os.environ.get("FEDERATION_SYNC_SERVER_API_KEY", "").strip()


async def mint_local_export_api_key(
    http: httpx.AsyncClient,
    gateway_api_base: str,
    *,
    drf_token: str,
) -> str:
    """Mint a FederationSync UserAPIKey via the local gateway."""
    url = mint_api_key_url(gateway_api_base)
    resp = await http.get(
        url,
        headers={"Authorization": f"Token {drf_token}"},
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        msg = f"expected dict from {url}, got {type(data).__name__}"
        raise TypeError(msg)
    raw = data.get("api_key")
    if not isinstance(raw, str) or not raw.strip():
        msg = f"mint response from {url} missing api_key"
        raise ValueError(msg)
    return raw.strip()


async def ensure_local_export_api_key(
    http: httpx.AsyncClient,
    gateway_api_base: str,
) -> str:
    """
    Resolve the Api-Key used for local gateway export.

    Prefer ``FEDERATION_SYNC_SERVER_API_KEY`` when set; otherwise mint using
    ``FEDERATION_SYNC_DRF_TOKEN`` and cache the raw key in the process env for
    subsequent bootstrap export calls.
    """
    existing = os.environ.get("FEDERATION_SYNC_SERVER_API_KEY", "").strip()
    if existing:
        return existing

    token = os.environ.get("FEDERATION_SYNC_DRF_TOKEN", "").strip()
    if not token:
        logger.warning(
            "Neither FEDERATION_SYNC_SERVER_API_KEY nor FEDERATION_SYNC_DRF_TOKEN "
            "is set; gateway export requests will be unauthenticated",
        )
        return ""

    try:
        api_key = await mint_local_export_api_key(
            http,
            gateway_api_base,
            drf_token=token,
        )
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        logger.error("Failed to mint federation sync Api-Key: {}", exc)
        return ""

    os.environ["FEDERATION_SYNC_SERVER_API_KEY"] = api_key
    logger.info("Minted federation sync export Api-Key from {}", gateway_api_base)
    return api_key


async def _get_json(
    http: httpx.AsyncClient,
    url: str,
    *,
    api_key: str,
    verify: str | bool = True,
) -> list | dict:
    headers = _gateway_auth_headers(api_key)
    if verify is not True and verify:
        async with httpx.AsyncClient(verify=verify, timeout=http.timeout) as client:
            resp = await client.get(url, headers=headers)
    else:
        resp = await http.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()


async def fetch_peer_export_list(
    http: httpx.AsyncClient,
    peer: PeerInfo,
    asset_type: AssetTypeEnum,
) -> list[FederatedDatasetDoc | FederatedCaptureDoc]:
    url = _export_list_url(peer, asset_type)
    api_key = _resolve_gateway_api_key(peer)
    data = await _get_json(
        http,
        url,
        api_key=api_key,
        verify=peer.ca_cert_path or True,
    )
    if not isinstance(data, list):
        msg = f"expected list from {url}, got {type(data).__name__}"
        raise TypeError(msg)
    doc_class = asset_doc_class(asset_type)
    return [doc_class.model_validate(item) for item in data]


async def bootstrap_gateway_exports(
    http: httpx.AsyncClient,
    peer: PeerInfo,
    indexer: FederatedAssetIndexer,
    *,
    event_at: datetime,
) -> int:
    """Pull all export lists for one gateway (local or remote). Returns doc count."""
    indexed = 0
    for asset_type in AssetTypeEnum:
        try:
            docs = await fetch_peer_export_list(http, peer, asset_type)
        except httpx.HTTPError as exc:
            logger.error(
                "bootstrap export failed for {} {}: {}",
                peer.name,
                asset_type.value,
                exc,
            )
            continue
        for doc in docs:
            if doc.site_name != peer.name:
                logger.error(
                    "bootstrap export failed for {} {}: site name mismatch "
                    "(doc.site_name={!r}, peer.name={!r})",
                    peer.name,
                    asset_type.value,
                    doc.site_name,
                    peer.name,
                )
                continue

            new_index = indexer.apply_asset_event(
                event_at=event_at,
                site_name=doc.site_name,
                asset=doc,
                asset_type=asset_type,
            )
            if new_index:
                indexed += 1
    return indexed


def _local_export_peer(config: FederationConfig) -> PeerInfo:
    return PeerInfo(
        name=config.site.name,
        fqdn=config.site.fqdn,
        display_name=config.site.display_name,
        gateway_api_base=config.gateway_api_base,
        sync_service_url=config.sync_service_url,
    )


async def bootstrap_local_site(
    http: httpx.AsyncClient,
    config: FederationConfig,
    indexer: FederatedAssetIndexer,
    *,
    event_at: datetime,
) -> int:
    peer = _local_export_peer(config)
    logger.info("Bootstrapping local public metadata from {}", peer.gateway_api_base)
    return await bootstrap_gateway_exports(http, peer, indexer, event_at=event_at)


async def bootstrap_all_peers(
    config: FederationConfig,
    http: httpx.AsyncClient,
    indexer: FederatedAssetIndexer,
    *,
    event_at: datetime,
) -> int:
    total = 0
    for peer in config.peers:
        logger.info("Bootstrapping peer {} from {}", peer.name, peer.gateway_api_base)
        total += await bootstrap_gateway_exports(
            http,
            peer,
            indexer,
            event_at=event_at,
        )
    return total


def _site_hello_payload(config: FederationConfig) -> SiteHelloWebhook:
    return SiteHelloWebhook(
        site_name=config.site.name,
        fqdn=config.site.fqdn,
        display_name=config.site.display_name,
        sync_service_url=config.sync_service_url,
        timestamp=datetime.now(UTC),
    )


async def push_site_hello_to_peer(
    http: httpx.AsyncClient,
    peer: PeerInfo,
    config: FederationConfig,
) -> dict:
    url = peer_webhook_url(peer, SITE_HELLO_PATH)
    body = _site_hello_payload(config).model_dump(mode="json")
    if peer.ca_cert_path:
        async with httpx.AsyncClient(
            verify=peer.ca_cert_path,
            timeout=http.timeout,
        ) as tls_client:
            resp = await tls_client.post(url, json=body)
    else:
        resp = await http.post(url, json=body)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        msg = f"expected dict response from site-hello, got {type(data).__name__}"
        raise TypeError(msg)
    return data


async def register_with_peers(
    http: httpx.AsyncClient,
    config: FederationConfig,
) -> None:
    for peer in config.peers:
        try:
            result = await push_site_hello_to_peer(http, peer, config)
        except httpx.HTTPError as exc:
            logger.error("site-hello to {} failed: {}", peer.name, exc)
            continue
        if result.get("status") != "registered":
            logger.error(
                "site-hello to {} unexpected response: {}",
                peer.name,
                result,
            )


async def run_bootstrap(
    config: FederationConfig,
    http: httpx.AsyncClient,
    indexer: FederatedAssetIndexer,
    *,
    event_at: datetime | None = None,
) -> None:
    """Backfill OpenSearch from gateway export lists, then register with peers.

    Post-save signals only cover new changes; existing public assets must be
    pulled from ``/federation/export/{datasets,captures}/`` on start.
    """
    at = event_at or datetime.now(UTC)
    await ensure_local_export_api_key(http, str(config.gateway_api_base))
    local_count = await bootstrap_local_site(http, config, indexer, event_at=at)
    peer_count = await bootstrap_all_peers(config, http, indexer, event_at=at)
    logger.info(
        "Bootstrap indexed {} local and {} peer export document(s)",
        local_count,
        peer_count,
    )
    await register_with_peers(http, config)
