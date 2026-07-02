import json
import os
from collections.abc import Awaitable
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

import httpx
import redis.asyncio as aioredis

from sds_federation.models import FederationConfig
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import AssetUpdatedWebhook
from sds_federation.schemas.webhooks import FederatedCaptureDoc
from sds_federation.schemas.webhooks import FederatedDatasetDoc
from sds_federation.schemas.webhooks import FederationEventType
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.peer_sync import push_asset_updated_to_peers
from sds_federation.services.redis_channel import resolve_federation_events_channel

type AssetResolver = Callable[
    [httpx.AsyncClient, FederationConfig, UUID, AssetTypeEnum],
    Awaitable[FederatedDatasetDoc | FederatedCaptureDoc],
]


def _export_path(asset_type: AssetTypeEnum) -> str:
    return "datasets" if asset_type == AssetTypeEnum.DATASET else "captures"


async def fetch_local_public_asset(
    http: httpx.AsyncClient,
    config: FederationConfig,
    uuid: UUID,
    asset_type: AssetTypeEnum,
) -> FederatedDatasetDoc | FederatedCaptureDoc:
    base = str(config.gateway_api_base).rstrip("/")
    url = f"{base}/federation/export/{_export_path(asset_type)}/{uuid}/"
    resp = await http.get(url)
    resp.raise_for_status()
    data = resp.json()
    if asset_type == AssetTypeEnum.DATASET:
        return FederatedDatasetDoc.model_validate(data)
    return FederatedCaptureDoc.model_validate(data)


def _tombstone_doc(
    config: FederationConfig,
    uuid: UUID,
    asset_type: AssetTypeEnum,
) -> FederatedDatasetDoc | FederatedCaptureDoc:
    if asset_type == AssetTypeEnum.DATASET:
        return FederatedDatasetDoc(
            uuid=uuid,
            site_name=config.site.name,
            name="",
            status="",
            status_display="",
        )
    return FederatedCaptureDoc(
        uuid=uuid,
        site_name=config.site.name,
        capture_type="",
    )


def parse_redis_event_payload(
    data: dict,
) -> tuple[AssetTypeEnum, FederationEventType, UUID, datetime] | None:
    """Parse a gateway-style federation:events message. Returns None if invalid."""
    try:
        asset_type = AssetTypeEnum(data.get("item_type"))
        event_type = FederationEventType(data["event_type"])
        uuid = UUID(data["uuid"])
        timestamp = datetime.fromisoformat(data["timestamp"])
    except (KeyError, TypeError, ValueError):
        return None
    return asset_type, event_type, uuid, timestamp


async def handle_redis_asset_event(
    http: httpx.AsyncClient,
    config: FederationConfig,
    indexer: FederatedAssetIndexer,
    *,
    asset_type: AssetTypeEnum,
    event_type: FederationEventType,
    uuid: UUID,
    timestamp: datetime,
    resolve_asset: AssetResolver | None = None,
) -> None:
    if event_type == FederationEventType.DELETED:
        asset = _tombstone_doc(config, uuid, asset_type)
    else:
        fetch = resolve_asset or fetch_local_public_asset
        asset = await fetch(http, config, uuid, asset_type)

    indexer.apply_asset_event(
        event_type=event_type,
        event_at=timestamp,
        site_name=config.site.name,
        asset=asset,
        asset_type=asset_type,
    )

    payload = AssetUpdatedWebhook(
        event_type=event_type,
        timestamp=timestamp,
        site_name=config.site.name,
        asset=asset,
        asset_type=asset_type,
    )
    await push_asset_updated_to_peers(http, config, payload)


async def dispatch_federation_redis_payload(
    http: httpx.AsyncClient,
    config: FederationConfig,
    indexer: FederatedAssetIndexer,
    data: dict,
    *,
    resolve_asset: AssetResolver | None = None,
) -> bool:
    """
    Handle one Redis pub/sub payload dict.

    Returns True if dispatched, False if the payload was ignored (invalid shape).
    """
    parsed = parse_redis_event_payload(data)
    if parsed is None:
        return False
    asset_type, event_type, uuid, timestamp = parsed
    await handle_redis_asset_event(
        http,
        config,
        indexer,
        asset_type=asset_type,
        event_type=event_type,
        uuid=uuid,
        timestamp=timestamp,
        resolve_asset=resolve_asset,
    )
    return True


async def run_federation_subscriber(
    redis_url: str,
    http: httpx.AsyncClient,
    config: FederationConfig,
    indexer: FederatedAssetIndexer,
    stop,
    *,
    channel: str | None = None,
) -> None:
    resolved_channel = channel or resolve_federation_events_channel(
        site_name=config.site.name,
        env_override=os.environ.get("FEDERATION_EVENTS_CHANNEL"),
    )
    client = aioredis.from_url(redis_url)
    pubsub = client.pubsub()
    await pubsub.subscribe(resolved_channel)
    try:
        async for message in pubsub.listen():
            if stop.is_set():
                break
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])

            await dispatch_federation_redis_payload(http, config, indexer, data)
    finally:
        await pubsub.unsubscribe(resolved_channel)
        await client.aclose()


def build_gateway_http_client() -> httpx.AsyncClient:
    api_key = os.environ.get("FEDERATION_GATEWAY_API_KEY", "")
    headers = {}
    if api_key:
        headers["Authorization"] = f"Api-Key: {api_key}"
    return httpx.AsyncClient(timeout=30.0, headers=headers)
