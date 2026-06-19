from datetime import UTC
from datetime import datetime

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request

from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import AssetUpdatedWebhook
from sds_federation.schemas.webhooks import SiteHelloWebhook
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.peer_registry import PeerRegistry

webhooks_router = APIRouter(tags=["webhooks"])


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


def _allowed_origin_sites(request: Request, payload: AssetUpdatedWebhook) -> None:
    config = request.app.state.config
    allowed = {peer.name for peer in config.peers} | {config.site.name}
    if payload.site_name not in allowed:
        raise HTTPException(status_code=403, detail="Unknown origin site")


@webhooks_router.post("/webhook/dataset-updated")
async def dataset_updated(payload: AssetUpdatedWebhook, request: Request) -> dict:
    _allowed_origin_sites(request, payload)
    if payload.asset is None or payload.asset_type is not AssetTypeEnum.DATASET:
        raise HTTPException(
            status_code=422,
            detail="Dataset body required for dataset-updated webhook.",
        )
    try:
        _indexer(request).apply_asset_event(
            event_type=payload.event_type,
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
    _allowed_origin_sites(request, payload)
    if payload.asset is None or payload.asset_type is not AssetTypeEnum.CAPTURE:
        raise HTTPException(
            status_code=422,
            detail="Capture body required for capture-updated webhook.",
        )
    try:
        _indexer(request).apply_asset_event(
            event_type=payload.event_type,
            event_at=payload.timestamp,
            site_name=payload.site_name,
            asset=payload.asset,
            asset_type=payload.asset_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "accepted"}


@webhooks_router.post("/webhook/site-hello")
async def site_hello(payload: SiteHelloWebhook, request: Request) -> dict:
    config = request.app.state.config
    if payload.site_name == config.site.name:
        raise HTTPException(
            status_code=422,
            detail="Cannot register self via site-hello",
        )
    allowed = {peer.name for peer in config.peers}
    if payload.site_name not in allowed:
        raise HTTPException(status_code=403, detail="Unknown registering site")

    hello = payload
    if hello.timestamp is None:
        hello = hello.model_copy(update={"timestamp": datetime.now(UTC)})

    _peer_registry(request).register(hello)
    return {"status": "registered", "site_name": hello.site_name}
