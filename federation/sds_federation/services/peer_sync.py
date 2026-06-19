import httpx
from loguru import logger

from sds_federation.models import FederationConfig
from sds_federation.schemas.webhooks import AssetUpdatedWebhook


def peer_webhook_url(peer, path: str) -> str:
    base = str(peer.sync_service_url).rstrip("/")
    return f"{base}/api/v1{path}"


async def push_asset_updated_to_peers(
    http: httpx.AsyncClient,
    config: FederationConfig,
    payload: AssetUpdatedWebhook,
) -> None:
    body = payload.model_dump(mode="json")
    path = payload.asset_type.webhook_path
    for peer in config.peers:
        url = peer_webhook_url(peer, path)
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
