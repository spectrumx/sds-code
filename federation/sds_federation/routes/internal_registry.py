from __future__ import annotations

import asyncio
import hmac
import os
from pathlib import Path

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel
from pydantic import Field

from sds_federation.schemas.registry import RegistrySite
from sds_federation.services.registry_challenge import CHALLENGE_MISMATCH_MESSAGE
from sds_federation.services.registry_challenge import challenge_matches
from sds_federation.services.registry_publish import publish_manifest
from sds_federation.services.registry_sign import RegistrySignError
from sds_federation.services.registry_verify import RegistryVerifyFetchError
from sds_federation.services.registry_verify import fetch_well_known_json


def require_admin_token(request: Request) -> None:
    expected = os.environ.get("FEDERATION_SYNC_ADMIN_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="admin token not configured")
    header = request.headers.get("Authorization", "")
    scheme, _, supplied = header.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        supplied.strip(), expected
    ):
        raise HTTPException(status_code=401, detail="unauthorized")


internal_registry_router = APIRouter(
    prefix="/internal/registry",
    dependencies=[Depends(require_admin_token)],
    tags=["internal-registry"],
)


class CapabilitiesOut(BaseModel):
    publish_enabled: bool
    site_fqdn: str
    key_configured: bool


class VerifyIn(BaseModel):
    fqdn: str
    challenge_hash: str


class VerifyOut(BaseModel):
    ok: bool
    error: str | None = None
    well_known: dict | None = None


class PublishIn(BaseModel):
    sites: list[RegistrySite] = Field(default_factory=list)
    min_serial: int | None = None
    dry_run: bool = False


class PublishOut(BaseModel):
    serial: int
    issued_at: str
    expires_at: str
    site_names: list[str]
    dry_run: bool


@internal_registry_router.get("/capabilities", response_model=CapabilitiesOut)
async def get_registry_capabilities(request: Request) -> CapabilitiesOut:
    config = request.app.state.config
    publish = config.registry.publish
    key_path = publish.signing_key_path.strip()
    key_ok = bool(key_path) and await asyncio.to_thread(Path(key_path).is_file)
    return CapabilitiesOut(
        publish_enabled=publish.enabled and key_ok,
        site_fqdn=config.site.fqdn,
        key_configured=key_ok,
    )


@internal_registry_router.post("/verify", response_model=VerifyOut)
async def verify(body: VerifyIn, request: Request) -> VerifyOut:
    config = request.app.state.config
    try:
        doc = await fetch_well_known_json(body.fqdn, config)
    except RegistryVerifyFetchError as exc:
        return VerifyOut(ok=False, error=str(exc))
    if not challenge_matches(doc, body.challenge_hash):
        return VerifyOut(ok=False, error=CHALLENGE_MISMATCH_MESSAGE)
    if str(doc.get("fqdn", "")).strip().lower() != body.fqdn.strip().lower():
        return VerifyOut(
            ok=False,
            error="fqdn in well-known JSON does not match this application.",
        )
    return VerifyOut(ok=True, well_known=doc)


@internal_registry_router.post("/publish", response_model=PublishOut)
async def publish(body: PublishIn, request: Request) -> PublishOut:
    config = request.app.state.config
    if not config.registry.publish.enabled:
        raise HTTPException(
            status_code=409, detail="publish is not enabled on this site"
        )
    try:
        result = await asyncio.to_thread(
            publish_manifest,
            config,
            body.sites,
            body.min_serial,
            dry_run=body.dry_run,
        )
    except RegistrySignError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return PublishOut(**result)
