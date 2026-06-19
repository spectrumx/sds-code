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
from sds_federation.schemas.webhooks import FederationEventType
from sds_federation.schemas.webhooks import SiteHelloWebhook
from sds_federation.services.peer_sync import peer_webhook_url

if TYPE_CHECKING:
    from sds_federation.services.fed_index import FederatedAssetIndexer

SITE_HELLO_PATH = "/webhook/site-hello"


def _export_list_url(peer: PeerInfo, asset_type: AssetTypeEnum) -> str:
    base = str(peer.gateway_api_base).rstrip("/")
    return f"{base}{asset_type.export_path}"


def _gateway_auth_headers(api_key: str) -> dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Api-Key: {api_key}"}


def _resolve_gateway_api_key(peer: PeerInfo) -> str:
    if peer.gateway_export_api_key:
        return peer.gateway_export_api_key
    return os.environ.get("FEDERATION_GATEWAY_API_KEY", "")


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
    data = await _get_json(http, url, api_key=api_key)
    if not isinstance(data, list):
        msg = f"expected list from {url}, got {type(data).__name__}"
        raise TypeError(msg)
    doc_class = asset_type.doc_class
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
            indexer.apply_asset_event(
                event_type=FederationEventType.UPDATED,
                event_at=event_at,
                site_name=doc.site_name,
                asset=doc,
                asset_type=asset_type,
            )
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
    when = event_at or datetime.now(UTC)
    local_count = await bootstrap_local_site(http, config, indexer, event_at=when)
    peer_count = await bootstrap_all_peers(http, config, indexer, event_at=when)
    logger.info(
        "Bootstrap indexed {} local + {} peer export documents",
        local_count,
        peer_count,
    )
    await register_with_peers(http, config)
