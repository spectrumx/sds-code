import asyncio
from datetime import UTC
from datetime import datetime

import httpx
from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from loguru import logger

from sds_federation.models import allowed_federated_origin_fqdns
from sds_federation.models import site_name_for_federation
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import AssetUpdatedWebhook
from sds_federation.schemas.webhooks import SiteHelloWebhook
from sds_federation.services.bootstrap import backfill_peer_on_hello
from sds_federation.services.bootstrap import peer_by_name
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.fed_index import alist_federated_assets_for_site
from sds_federation.services.peer_registry import PeerRegistry
from sds_federation.services.peer_sync import peer_for_outbound

webhooks_router = APIRouter(tags=["webhooks"])


def _opensearch(request: Request):
    client = getattr(request.app.state, "opensearch_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="OpenSearch not ready")
    return client


def _local_site_name(request: Request) -> str:
    config = getattr(request.app.state, "config", None)
    if config is None:
        raise HTTPException(status_code=503, detail="Config not ready")
    return site_name_for_federation(config.site)


def _indexer(request: Request) -> FederatedAssetIndexer:
    indexer = getattr(request.app.state, "fed_indexer", None)
    if indexer is None:
        raise HTTPException(status_code=503, detail="Indexer not ready")
    return indexer


def _peer_registry(request: Request) -> PeerRegistry:
    registry = getattr(request.app.state, "peer_registry", None)
    if registry is None:
        raise HTTPException(status_code=503, detail="Peer registry not ready")
    return registry


def _http_client(request: Request) -> httpx.AsyncClient | None:
    return getattr(request.app.state, "http", None)


def _allowed_origin_sites(request: Request, payload: AssetUpdatedWebhook) -> None:
    config = request.app.state.config
    if payload.site_name == site_name_for_federation(config.site):
        raise HTTPException(
            status_code=403,
            detail="Local site metadata is not accepted via peer webhooks",
        )

    allowed = allowed_federated_origin_fqdns(config)
    if payload.site_name not in allowed:
        raise HTTPException(status_code=403, detail="Unknown origin site")


@webhooks_router.post("/webhook/dataset-updated")
async def dataset_updated(payload: AssetUpdatedWebhook, request: Request) -> dict:
    """
    Handle dataset-updated webhook from another site.
    Index the dataset in the local site's OpenSearch.
    """
    _allowed_origin_sites(request, payload)
    if payload.asset is None or payload.asset_type is not AssetTypeEnum.DATASET:
        raise HTTPException(
            status_code=422,
            detail="Dataset body required for dataset-updated webhook.",
        )
    try:
        await asyncio.to_thread(
            _indexer(request).apply_asset_event,
            event_at=payload.timestamp,
            site_name=payload.site_name,
            asset=payload.asset,
            asset_type=payload.asset_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "accepted"}


@webhooks_router.post("/webhook/capture-updated")
async def capture_updated(payload: AssetUpdatedWebhook, request: Request) -> dict:
    """
    Handle capture-updated webhook from another site.
    Index the capture in the local site's OpenSearch.
    """
    _allowed_origin_sites(request, payload)
    if payload.asset is None or payload.asset_type is not AssetTypeEnum.CAPTURE:
        raise HTTPException(
            status_code=422,
            detail="Capture body required for capture-updated webhook.",
        )
    try:
        await asyncio.to_thread(
            _indexer(request).apply_asset_event,
            event_at=payload.timestamp,
            site_name=payload.site_name,
            asset=payload.asset,
            asset_type=payload.asset_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "accepted"}


@webhooks_router.get("/webhook/list-datasets/")
async def list_datasets(request: Request) -> list[dict]:
    """
    List all datasets for the local site to new peer on bootstrap.
    """
    docs = await alist_federated_assets_for_site(
        _opensearch(request),
        site_name=_local_site_name(request),
        asset_type=AssetTypeEnum.DATASET,
    )
    return [doc.model_dump(mode="json") for doc in docs]


@webhooks_router.get("/webhook/list-captures/")
async def list_captures(request: Request) -> list[dict]:
    """
    List all captures for the local site to new peer on bootstrap.
    """
    docs = await alist_federated_assets_for_site(
        _opensearch(request),
        site_name=_local_site_name(request),
        asset_type=AssetTypeEnum.CAPTURE,
    )
    return [doc.model_dump(mode="json") for doc in docs]


@webhooks_router.post("/webhook/site-hello")
async def site_hello(payload: SiteHelloWebhook, request: Request) -> dict:
    config = request.app.state.config
    if payload.site_name == site_name_for_federation(config.site):
        raise HTTPException(
            status_code=422,
            detail="Cannot register self via site-hello",
        )
    allowed = {peer.fqdn for peer in config.peers}
    if payload.site_name not in allowed:
        raise HTTPException(status_code=403, detail="Unknown registering site")

    hello = payload
    if hello.timestamp is None:
        hello = hello.model_copy(update={"timestamp": datetime.now(UTC)})

    _peer_registry(request).register(hello)

    peer = peer_by_name(config, hello.site_name)
    http = _http_client(request)
    if peer is None:
        logger.error(
            "site-hello from {}: peer missing from config after allowlist check",
            hello.site_name,
        )
    elif http is None:
        logger.warning(
            "site-hello from {}: no HTTP client on app state; skipping export backfill",
            hello.site_name,
        )
    else:
        outbound = peer_for_outbound(peer, _peer_registry(request))
        try:
            indexed = await backfill_peer_on_hello(
                http,
                outbound,
                _indexer(request),
            )
            logger.info(
                "site-hello backfill indexed {} document(s) from {} ({})",
                indexed,
                outbound.name,
                outbound.sync_service_url,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("site-hello backfill failed for {}: {}", outbound.name, exc)

    return {"status": "registered", "site_name": hello.site_name}
