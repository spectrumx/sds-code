import json
import os
from collections.abc import Awaitable
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

import httpx
import redis.asyncio as aioredis
from loguru import logger as log
from opensearchpy import OpenSearch

from sds_federation.models import FederationConfig
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import AssetUpdatedWebhook
from sds_federation.schemas.webhooks import FederatedCaptureDoc
from sds_federation.schemas.webhooks import FederatedDatasetDoc
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.fed_search import aload_federated_asset
from sds_federation.services.peer_registry import PeerRegistry
from sds_federation.services.peer_sync import push_asset_updated_to_peers
from sds_federation.services.redis_channel import resolve_federation_events_channel

type AssetLoader = Callable[
    [OpenSearch, FederationConfig, UUID, AssetTypeEnum],
    Awaitable[FederatedDatasetDoc | FederatedCaptureDoc | None],
]


def parse_redis_event_payload(
    data: dict,
) -> tuple[AssetTypeEnum, UUID, datetime] | None:
    """Parse a gateway-style federation:events message. Returns None if invalid."""
    try:
        asset_type = AssetTypeEnum(data.get("item_type"))
        uuid = UUID(data["uuid"])
        timestamp = datetime.fromisoformat(data["timestamp"])
    except (KeyError, TypeError, ValueError):
        return None
    return asset_type, uuid, timestamp


async def _default_load_asset(
    os_client: OpenSearch,
    config: FederationConfig,
    uuid: UUID,
    asset_type: AssetTypeEnum,
) -> FederatedDatasetDoc | FederatedCaptureDoc | None:
    return await aload_federated_asset(
        os_client,
        site_name=config.site.name,
        uuid=uuid,
        asset_type=asset_type,
    )


async def _load_local_asset(
    os_client: OpenSearch,
    config: FederationConfig,
    uuid: UUID,
    asset_type: AssetTypeEnum,
    *,
    load_asset: AssetLoader | None = None,
) -> FederatedDatasetDoc | FederatedCaptureDoc | None:
    loader = load_asset or _default_load_asset
    return await loader(os_client, config, uuid, asset_type)


async def handle_redis_asset_event(
    http: httpx.AsyncClient,
    config: FederationConfig,
    os_client: OpenSearch,
    *,
    asset_type: AssetTypeEnum,
    uuid: UUID,
    timestamp: datetime,
    load_asset: AssetLoader | None = None,
    registry: PeerRegistry | None = None,
) -> None:
    """Read local doc from OpenSearch (gateway indexes on save) and fan out to peers."""
    asset = await _load_local_asset(
        os_client,
        config,
        uuid,
        asset_type,
        load_asset=load_asset,
    )
    if asset is None:
        log.warning(
            "No fed-* document for {} {} after Redis event; skipping peer push",
            asset_type.value,
            uuid,
        )
        return

    payload = AssetUpdatedWebhook(
        timestamp=timestamp,
        site_name=config.site.name,
        asset=asset,
        asset_type=asset_type,
    )
    await push_asset_updated_to_peers(http, config, payload, registry)


async def dispatch_federation_redis_payload(
    http: httpx.AsyncClient,
    config: FederationConfig,
    os_client: OpenSearch,
    indexer: FederatedAssetIndexer,
    data: dict,
    *,
    load_asset: AssetLoader | None = None,
    registry: PeerRegistry | None = None,
) -> bool:
    """
    Handle one Redis pub/sub payload dict.

    Returns True if dispatched, False if the payload was ignored (invalid shape).
    """
    _ = indexer
    parsed = parse_redis_event_payload(data)
    if parsed is None:
        return False
    asset_type, uuid, timestamp = parsed
    await handle_redis_asset_event(
        http,
        config,
        os_client,
        asset_type=asset_type,
        uuid=uuid,
        timestamp=timestamp,
        load_asset=load_asset,
        registry=registry,
    )
    return True


async def run_federation_subscriber(
    redis_url: str,
    http: httpx.AsyncClient,
    config: FederationConfig,
    os_client: OpenSearch,
    indexer: FederatedAssetIndexer,
    stop,
    *,
    channel: str | None = None,
    registry: PeerRegistry | None = None,
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

            await dispatch_federation_redis_payload(
                http,
                config,
                os_client,
                indexer,
                data,
                registry=registry,
            )
    finally:
        await pubsub.unsubscribe(resolved_channel)
        await client.aclose()


def build_peer_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30.0)


def build_gateway_http_client() -> httpx.AsyncClient:
    """Deprecated alias for peer webhook HTTP client."""
    return build_peer_http_client()
