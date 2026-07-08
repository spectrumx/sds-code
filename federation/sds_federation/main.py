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


def _bootstrap_enabled() -> bool:
    return os.environ.get("FEDERATION_BOOTSTRAP_ON_START", "true").lower() not in (
        "0",
        "false",
        "no",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_federation_config()
    http = build_gateway_http_client()
    os_host = os.environ.get("OPENSEARCH_HOST", "opensearch")
    os_port = os.environ.get("OPENSEARCH_PORT", "9200")
    os_client = OpenSearch(hosts=[{"host": os_host, "port": int(os_port)}])
    app.state.config = config
    app.state.http = http
    app.state.opensearch_client = os_client
    app.state.fed_indexer = FederatedAssetIndexer(os_client)
    app.state.peer_registry = PeerRegistry()

    if _bootstrap_enabled():
        try:
            await run_bootstrap(
                config,
                http,
                app.state.fed_indexer,
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
            app.state.fed_indexer,
            stop,
        ),
    )
    app.state.subscriber_task = sub_task

    yield

    stop.set()
    sub_task.cancel()
    with suppress(asyncio.CancelledError):
        await sub_task
    await http.aclose()


app = FastAPI(title="SDS Federation Sync", root_path="/sync", lifespan=lifespan)
app.include_router(health_router)
app.include_router(webhooks_router, prefix=API_PREFIX)
