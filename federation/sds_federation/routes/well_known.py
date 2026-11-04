from __future__ import annotations

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.responses import Response

from sds_federation.services.registry_publish import read_published_manifest_bytes
from sds_federation.services.registry_publish import read_published_signature_bytes
from sds_federation.services.well_known import WELL_KNOWN_SDS_FEDERATION_PATH
from sds_federation.services.well_known import build_site_document
from sds_federation.services.well_known import document_ready

well_known_router = APIRouter(tags=["well-known"])

REGISTRY_SITES_PATH = "/.well-known/sds-registry/sites.json"
REGISTRY_SIG_PATH = "/.well-known/sds-registry/sites.json.sig"


@well_known_router.get(WELL_KNOWN_SDS_FEDERATION_PATH)
async def sds_federation_well_known(request: Request) -> JSONResponse:
    config = request.app.state.config
    doc = build_site_document(config)
    if not document_ready(doc):
        raise HTTPException(
            status_code=503, detail="well-known document is not configured"
        )
    return JSONResponse(content=doc, headers={"Cache-Control": "no-store"})


@well_known_router.get(REGISTRY_SITES_PATH)
async def registry_sites_json(request: Request) -> Response:
    config = request.app.state.config
    if not config.registry.publish.enabled:
        raise HTTPException(
            status_code=404, detail="registry manifest is not published"
        )
    payload = read_published_manifest_bytes(config)
    if payload is None:
        raise HTTPException(
            status_code=404, detail="registry manifest is not published"
        )
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=60"},
    )


@well_known_router.get(REGISTRY_SIG_PATH)
async def registry_sites_sig(request: Request) -> Response:
    config = request.app.state.config
    if not config.registry.publish.enabled:
        raise HTTPException(
            status_code=404, detail="registry manifest is not published"
        )
    payload = read_published_signature_bytes(config)
    if payload is None:
        raise HTTPException(
            status_code=404, detail="registry manifest is not published"
        )
    return Response(
        content=payload,
        media_type="text/plain",
        headers={"Cache-Control": "public, max-age=60"},
    )
