import asyncio
import os
from contextlib import asynccontextmanager
from contextlib import suppress
from datetime import UTC
from datetime import datetime

from fastapi import FastAPI
from loguru import logger
from opensearchpy import OpenSearch

from sds_federation.models import load_federation_config
from sds_federation.routes.health import health_router
from sds_federation.routes.webhooks import webhooks_router
from sds_federation.services.bootstrap import run_bootstrap
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.local_events import build_gateway_http_client
from sds_federation.services.local_events import run_federation_subscriber
from sds_federation.services.peer_registry import PeerRegistry

API_PREFIX = "/api/v1"
SYNC_PREFIX = "/sync"


def _bootstrap_enabled() -> bool:
    return os.environ.get("FEDERATION_BOOTSTRAP_ON_START", "true").lower() not in (
        "0",
        "false",
        "no",
    )


sync_app = FastAPI(title="SDS Federation Sync")
sync_app.include_router(health_router)
sync_app.include_router(webhooks_router, prefix=API_PREFIX)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_federation_config()
    http = build_gateway_http_client()

    # TODO: Create a shared OpenSearch client for both apps in a later PR.
    os_host = os.environ.get("OPENSEARCH_HOST", "opensearch")
    os_port = os.environ.get("OPENSEARCH_PORT", "9200")
    os_client = OpenSearch(hosts=[{"host": os_host, "port": int(os_port)}])
    peer_registry = PeerRegistry()
    fed_indexer = FederatedAssetIndexer(os_client)

    # Mounted sync_app owns webhook/health state; keep root app in sync for lifespan.
    for target in (app, sync_app):
        target.state.config = config
        target.state.http = http
        target.state.opensearch_client = os_client
        target.state.fed_indexer = fed_indexer
        target.state.peer_registry = peer_registry

    if _bootstrap_enabled():
        try:
            await run_bootstrap(
                config,
                http,
                fed_indexer,
                event_at=datetime.now(UTC),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Federation bootstrap failed: {}", exc)
    else:
        logger.info(
            "Federation bootstrap skipped (FEDERATION_BOOTSTRAP_ON_START=false)",
        )

    stop = asyncio.Event()
    redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
    sub_task = asyncio.create_task(
        run_federation_subscriber(
            redis_url,
            http,
            config,
            os_client,
            fed_indexer,
            stop,
            registry=peer_registry,
        ),
    )
    app.state.subscriber_task = sub_task
    sync_app.state.subscriber_task = sub_task

    yield

    stop.set()
    sub_task.cancel()
    with suppress(asyncio.CancelledError):
        await sub_task
    await http.aclose()


app = FastAPI(title="SDS Federation", lifespan=lifespan)
app.mount(SYNC_PREFIX, sync_app)
