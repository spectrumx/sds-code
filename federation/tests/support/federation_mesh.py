"""In-process multi-site federation mesh for integration tests."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

import httpx
from fastapi import FastAPI
from sds_federation.models import FederationConfig
from sds_federation.models import PeerInfo
from sds_federation.models import SiteInfo
from sds_federation.routes.webhooks import webhooks_router
from sds_federation.services.fed_index import FederatedAssetIndexer

from tests.support.gateway_export_mock import GatewayExportCatalog
from tests.support.gateway_export_mock import handle_gateway_export_request
from tests.support.mock_opensearch import RecordingOpenSearch
from tests.support.mock_peer_registry import RecordingPeerRegistry

API_PREFIX = "/api/v1"

TESTSITE_SYNC_ORIGIN = "http://testsite.test"
PEER_ONE_SYNC_ORIGIN = "http://peer-one.test"
TESTSITE_GATEWAY_HOST = "testsite-gateway.test"
PEER_ONE_GATEWAY_HOST = "peer-one-gateway.test"


def testsite_config() -> FederationConfig:
    return FederationConfig(
        site=SiteInfo(
            name="testsite",
            fqdn="localhost",
            display_name="Test Site",
        ),
        gateway_api_base=f"http://{TESTSITE_GATEWAY_HOST}/api/v1",
        sync_service_url=f"{TESTSITE_SYNC_ORIGIN}/sync",
        peers=[
            PeerInfo(
                name="peer-one",
                fqdn="peer.test",
                display_name="Peer One",
                gateway_api_base=f"http://{PEER_ONE_GATEWAY_HOST}/api/v1",
                sync_service_url=f"{PEER_ONE_SYNC_ORIGIN}/sync",
            ),
        ],
    )


def peer_one_config() -> FederationConfig:
    return FederationConfig(
        site=SiteInfo(
            name="peer-one",
            fqdn="peer.test",
            display_name="Peer Site",
        ),
        gateway_api_base=f"http://{PEER_ONE_GATEWAY_HOST}/api/v1",
        sync_service_url=f"{PEER_ONE_SYNC_ORIGIN}/sync",
        peers=[
            PeerInfo(
                name="testsite",
                fqdn="localhost",
                display_name="Test Site",
                gateway_api_base=f"http://{TESTSITE_GATEWAY_HOST}/api/v1",
                sync_service_url=f"{TESTSITE_SYNC_ORIGIN}/sync",
            ),
        ],
    )


def build_sync_app(
    config: FederationConfig,
    indexer: FederatedAssetIndexer,
    registry: RecordingPeerRegistry | None = None,
) -> FastAPI:
    """Outer app mounts sync routes at /sync (matches production Traefik path)."""
    sync_app = FastAPI()
    sync_app.state.config = config
    sync_app.state.fed_indexer = indexer
    sync_app.state.peer_registry = registry or RecordingPeerRegistry()
    sync_app.include_router(webhooks_router, prefix=API_PREFIX)
    root = FastAPI()
    root.mount("/sync", sync_app)
    return root


@dataclass
class SyncSite:
    name: str
    config: FederationConfig
    app: FastAPI
    opensearch: RecordingOpenSearch
    registry: RecordingPeerRegistry


@dataclass
class FederationMesh:
    sites: dict[str, SyncSite]
    http: httpx.AsyncClient
    gateway_catalog: GatewayExportCatalog
    recorded_webhooks: list[httpx.Request] = field(default_factory=list)

    def site(self, name: str) -> SyncSite:
        return self.sites[name]


class FederationMeshTransport(httpx.AsyncBaseTransport):
    """Route sync hosts to ASGI apps; gateway hosts to export catalog."""

    def __init__(
        self,
        sync_apps_by_host: dict[str, FastAPI],
        gateway_catalog: GatewayExportCatalog,
        recorded_webhooks: list[httpx.Request],
    ) -> None:
        self._sync_apps = sync_apps_by_host
        self._gateway_catalog = gateway_catalog
        self._recorded_webhooks = recorded_webhooks

    async def handle_async_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        if request.method == "POST" and "/webhook/" in request.url.path:
            self._recorded_webhooks.append(request)

        export_response = handle_gateway_export_request(
            request,
            self._gateway_catalog,
        )
        if export_response is not None:
            return export_response

        host = request.url.host
        if not host:
            return httpx.Response(400, json={"detail": "missing host"})

        app = self._sync_apps.get(host)
        if app is None:
            return httpx.Response(
                404,
                json={"detail": f"no sync app registered for host {host!r}"},
            )

        transport = httpx.ASGITransport(app=app)
        async with transport as asgi:
            return await asgi.handle_async_request(request)


def build_federation_mesh(
    *,
    configs: dict[str, FederationConfig] | None = None,
) -> FederationMesh:
    if configs is None:
        configs = {
            "testsite": testsite_config(),
            "peer-one": peer_one_config(),
        }

    recorded: list[httpx.Request] = []
    catalog = GatewayExportCatalog()
    sites: dict[str, SyncSite] = {}
    sync_apps: dict[str, FastAPI] = {}

    for name, config in configs.items():
        opensearch = RecordingOpenSearch()
        registry = RecordingPeerRegistry()
        indexer = FederatedAssetIndexer(opensearch)
        app = build_sync_app(config, indexer, registry)
        sites[name] = SyncSite(
            name=name,
            config=config,
            app=app,
            opensearch=opensearch,
            registry=registry,
        )
        sync_host = httpx.URL(str(config.sync_service_url)).host
        if sync_host:
            sync_apps[sync_host] = app

    transport = FederationMeshTransport(sync_apps, catalog, recorded)
    http = httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(10.0),
    )
    return FederationMesh(
        sites=sites,
        http=http,
        gateway_catalog=catalog,
        recorded_webhooks=recorded,
    )


async def close_mesh(mesh: FederationMesh) -> None:
    await mesh.http.aclose()
