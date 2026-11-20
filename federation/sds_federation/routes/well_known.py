from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.responses import Response

from sds_federation.services.registry_publish import read_published_manifest_bytes
from sds_federation.services.registry_publish import read_published_signature_bytes
from sds_federation.services.registry_sign import REGISTRY_VERIFYING_PUBKEY_WELL_KNOWN_NAME
from sds_federation.services.registry_sign import RegistrySignError
from sds_federation.services.registry_sign import read_verifying_public_key_pem_bytes
from sds_federation.services.well_known import WELL_KNOWN_SDS_FEDERATION_PATH
from sds_federation.services.well_known import build_site_document
from sds_federation.services.well_known import document_ready

if TYPE_CHECKING:
    from collections.abc import Callable

    from sds_federation.models import FederationConfig

well_known_router = APIRouter(tags=["well-known"])

REGISTRY_SITES_PATH = "/.well-known/sds-registry/sites.json"
REGISTRY_SIG_PATH = "/.well-known/sds-registry/sites.json.sig"
REGISTRY_PUBKEY_PATH = (
    f"/.well-known/sds-registry/{REGISTRY_VERIFYING_PUBKEY_WELL_KNOWN_NAME}"
)


@well_known_router.get(WELL_KNOWN_SDS_FEDERATION_PATH)
async def sds_federation_well_known(request: Request) -> JSONResponse:
    config = request.app.state.config
    doc = build_site_document(config)
    if not document_ready(doc):
        raise HTTPException(
            status_code=503, detail="well-known document is not configured"
        )
    return JSONResponse(content=doc, headers={"Cache-Control": "no-store"})


async def _serve_published(
    request: Request,
    reader: Callable[[FederationConfig], bytes | None],
    media_type: str,
) -> Response:
    config = request.app.state.config
    payload = None
    if config.registry.publish.enabled:
        try:
            payload = await asyncio.to_thread(reader, config)
        except RegistrySignError:
            payload = None
    if payload is None:
        raise HTTPException(
            status_code=404, detail="registry manifest is not published"
        )
    return Response(
        content=payload,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=60"},
    )


@well_known_router.get(REGISTRY_SITES_PATH)
async def registry_sites_json(request: Request) -> Response:
    return await _serve_published(
        request, read_published_manifest_bytes, "application/json"
    )


@well_known_router.get(REGISTRY_SIG_PATH)
async def registry_sites_sig(request: Request) -> Response:
    return await _serve_published(request, read_published_signature_bytes, "text/plain")


@well_known_router.get(REGISTRY_PUBKEY_PATH)
async def registry_verifying_public_key_pem(request: Request) -> Response:
    config = request.app.state.config
    if not config.registry.publish.enabled:
        raise HTTPException(
            status_code=404,
            detail="registry public key is not published",
        )
    pubkey_path = str(config.registry.public_key_path)

    def _read() -> bytes | None:
        return read_verifying_public_key_pem_bytes(pubkey_path)

    payload = await asyncio.to_thread(_read)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="registry public key is not published",
        )
    return Response(
        content=payload,
        media_type="application/x-pem-file",
        headers={"Cache-Control": "public, max-age=3600"},
    )
