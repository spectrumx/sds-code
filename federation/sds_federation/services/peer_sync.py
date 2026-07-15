from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from loguru import logger

if TYPE_CHECKING:
    from sds_federation.models import FederationConfig
    from sds_federation.models import PeerInfo
    from sds_federation.schemas.webhooks import AssetUpdatedWebhook
    from sds_federation.services.peer_registry import PeerRegistry


def peer_webhook_url(peer: PeerInfo, path: str) -> str:
    base = str(peer.sync_service_url).rstrip("/")
    return f"{base}/api/v1{path}"


def peer_for_outbound(
    peer: PeerInfo,
    registry: PeerRegistry | None,
) -> PeerInfo:
    """Return peer with sync_service_url overlaid from site-hello when present."""
    if registry is None:
        return peer
    hello = registry.get(peer.name)
    if hello is None:
        return peer
    return peer.model_copy(update={"sync_service_url": hello.sync_service_url})


async def push_asset_updated_to_peers(
    http: httpx.AsyncClient,
    config: FederationConfig,
    payload: AssetUpdatedWebhook,
    registry: PeerRegistry | None = None,
) -> None:
    body = payload.model_dump(mode="json")
    path = payload.asset_type.webhook_path
    for peer in config.peers:
        outbound = peer_for_outbound(peer, registry)
        url = peer_webhook_url(outbound, path)
        try:
            if peer.ca_cert_path:
                async with httpx.AsyncClient(
                    verify=peer.ca_cert_path,
                    timeout=http.timeout,
                ) as tls_client:
                    resp = await tls_client.post(url, json=body)
            else:
                resp = await http.post(url, json=body)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("webhook to {} failed: {}", peer.name, exc)
