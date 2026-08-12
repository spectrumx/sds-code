"""Bootstrap federated metadata from gateway export APIs and register with peers."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING

import httpx
from loguru import logger

from sds_federation.models import FederationConfig
from sds_federation.models import PeerInfo
from sds_federation.models import site_name_for_federation
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import FederatedCaptureDoc
from sds_federation.schemas.webhooks import FederatedDatasetDoc
from sds_federation.schemas.webhooks import SiteHelloWebhook
from sds_federation.schemas.webhooks import asset_doc_class
from sds_federation.services.peer_http import peer_request
from sds_federation.services.peer_sync import peer_webhook_url

if TYPE_CHECKING:
    from sds_federation.services.fed_index import FederatedAssetIndexer

SITE_HELLO_PATH = "/webhook/site-hello"
_MINT_PATH = "/users/get-federation-sync-api-key/"
# Peer sync often receives site-hello while the peer process is still binding.
_PEER_LIST_ATTEMPTS = 5
_PEER_LIST_BACKOFF_SECS = 0.5
_HTTP_INTERNAL_ERROR = 500


def _export_list_url(peer: PeerInfo, asset_type: AssetTypeEnum) -> str:
    base = str(peer.gateway_api_base).rstrip("/")
    return f"{base}{asset_type.export_path}"


def _webhook_list_url(peer: PeerInfo, asset_type: AssetTypeEnum) -> str:
    return peer_webhook_url(peer, asset_type.webhook_list_path)


def _gateway_origin(gateway_api_base: str) -> str:
    """Strip ``/api/v1`` (or ``/api/<version>``) so non-API routes resolve."""
    base = str(gateway_api_base).rstrip("/")
    if base.endswith("/api/v1"):
        return base[: -len("/api/v1")]
    marker = "/api/"
    if marker in base:
        return base.rsplit(marker, 1)[0]
    return base


def mint_api_key_url(gateway_api_base: str) -> str:
    """Gateway mint lives at ``/users/...``, not under ``/api/v1``."""
    return f"{_gateway_origin(gateway_api_base)}{_MINT_PATH}"


def _gateway_auth_headers(api_key: str) -> dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Api-Key: {api_key}"}


def _resolve_local_gateway_api_key() -> str:
    """Api-Key for this site's gateway export only (never for remote peers)."""
    return os.environ.get("FEDERATION_SYNC_SERVER_API_KEY", "").strip()


async def mint_local_export_api_key(
    http: httpx.AsyncClient,
    gateway_api_base: str,
    *,
    drf_token: str,
) -> str:
    """Mint a FederationSync UserAPIKey via the local gateway."""
    url = mint_api_key_url(gateway_api_base)
    resp = await http.get(
        url,
        headers={"Authorization": f"Token {drf_token}"},
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        msg = f"expected dict from {url}, got {type(data).__name__}"
        raise TypeError(msg)
    raw = data.get("api_key")
    if not isinstance(raw, str) or not raw.strip():
        msg = f"mint response from {url} missing api_key"
        raise ValueError(msg)
    return raw.strip()


async def ensure_local_export_api_key(
    http: httpx.AsyncClient,
    gateway_api_base: str,
) -> str:
    """
    Resolve the Api-Key used for local gateway export.

    Prefer ``FEDERATION_SYNC_SERVER_API_KEY`` when set; otherwise mint using
    ``FEDERATION_SYNC_DRF_TOKEN`` and cache the raw key in the process env for
    subsequent bootstrap export calls.
    """
    existing = os.environ.get("FEDERATION_SYNC_SERVER_API_KEY", "").strip()
    if existing:
        return existing

    token = os.environ.get("FEDERATION_SYNC_DRF_TOKEN", "").strip()
    if not token:
        logger.warning(
            "Neither FEDERATION_SYNC_SERVER_API_KEY nor FEDERATION_SYNC_DRF_TOKEN "
            "is set; gateway export requests will be unauthenticated",
        )
        return ""

    try:
        api_key = await mint_local_export_api_key(
            http,
            gateway_api_base,
            drf_token=token,
        )
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        logger.error("Failed to mint federation sync Api-Key: {}", exc)
        return ""

    os.environ["FEDERATION_SYNC_SERVER_API_KEY"] = api_key
    logger.info("Minted federation sync export Api-Key from {}", gateway_api_base)
    return api_key


async def _get_json(
    http: httpx.AsyncClient,
    url: str,
    *,
    api_key: str,
    ca_cert_path: str = "",
) -> list | dict:
    headers = _gateway_auth_headers(api_key)
    resp = await peer_request(
        http,
        "GET",
        url,
        ca_cert_path=ca_cert_path,
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json()


async def fetch_gateway_export_list(
    http: httpx.AsyncClient,
    peer: PeerInfo,
    asset_type: AssetTypeEnum,
    *,
    api_key: str,
) -> list[FederatedDatasetDoc | FederatedCaptureDoc]:
    """Pull public export list from local site gateway (postgres)."""
    url = _export_list_url(peer, asset_type)
    data = await _get_json(
        http,
        url,
        api_key=api_key,
        ca_cert_path=peer.ca_cert_path,
    )
    if not isinstance(data, list):
        msg = f"expected list from {url}, got {type(data).__name__}"
        raise TypeError(msg)
    doc_class = asset_doc_class(asset_type)
    return [doc_class.model_validate(item) for item in data]


def _is_retryable_peer_list_error(exc: BaseException) -> bool:
    """True for transient connect/read failures while a peer sync is starting."""
    if isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            httpx.RemoteProtocolError,
        ),
    ):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= _HTTP_INTERNAL_ERROR
    return False


async def fetch_peer_sync_list(
    http: httpx.AsyncClient,
    peer: PeerInfo,
    asset_type: AssetTypeEnum,
    *,
    attempts: int = _PEER_LIST_ATTEMPTS,
    backoff_secs: float = _PEER_LIST_BACKOFF_SECS,
) -> list[FederatedDatasetDoc | FederatedCaptureDoc]:
    """Pull peer-owned docs from the peer sync service (fed-* OpenSearch export).

    Retries transient connection/5xx errors so site-hello backfill survives peer
    startup races.
    """
    url = _webhook_list_url(peer, asset_type)
    last_exc: httpx.HTTPError | None = None
    tries = max(1, attempts)
    for attempt in range(1, tries + 1):
        try:
            data = await _get_json(
                http,
                url,
                api_key="",
                ca_cert_path=peer.ca_cert_path,
            )
            if not isinstance(data, list):
                msg = f"expected list from {url}, got {type(data).__name__}"
                raise TypeError(msg)
            doc_class = asset_doc_class(asset_type)
            return [doc_class.model_validate(item) for item in data]
        except httpx.HTTPError as exc:
            last_exc = exc
            if not _is_retryable_peer_list_error(exc) or attempt >= tries:
                raise
            logger.warning(
                "peer sync list {} {} attempt {}/{} failed ({}); retrying in {:.1f}s",
                peer.name,
                asset_type.value,
                attempt,
                tries,
                exc,
                backoff_secs * attempt,
            )
            await asyncio.sleep(backoff_secs * attempt)
    assert last_exc is not None
    raise last_exc


def _parse_doc_event_at(
    doc: FederatedDatasetDoc | FederatedCaptureDoc,
    *,
    fallback: datetime,
) -> datetime:
    """Prefer asset updated_at so bootstrap does not stamp a shared 'now'."""
    for raw in (doc.updated_at, doc.created_at):
        if isinstance(raw, datetime):
            return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = datetime.fromisoformat(raw)
            except ValueError:
                continue
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return fallback


def _index_export_docs(
    indexer: FederatedAssetIndexer,
    peer: PeerInfo,
    asset_type: AssetTypeEnum,
    docs: list[FederatedDatasetDoc | FederatedCaptureDoc],
    *,
    fallback_event_at: datetime,
) -> int:
    indexed = 0
    for doc in docs:
        if doc.site_name != site_name_for_federation(peer):
            logger.error(
                "bootstrap export failed for {} {}: site name (FQDN) mismatch "
                "(doc.site_name={!r}, peer.fqdn={!r})",
                peer.name,
                asset_type.value,
                doc.site_name,
                site_name_for_federation(peer),
            )
            continue

        event_at = _parse_doc_event_at(doc, fallback=fallback_event_at)
        new_index = indexer.apply_asset_event(
            event_at=event_at,
            site_name=doc.site_name,
            asset=doc,
            asset_type=asset_type,
        )
        if new_index:
            indexed += 1
    return indexed


async def bootstrap_gateway_exports(
    http: httpx.AsyncClient,
    peer: PeerInfo,
    indexer: FederatedAssetIndexer,
    *,
    event_at: datetime | None = None,
) -> int:
    """Pull gateway export lists for the local site. Returns newly indexed count."""
    api_key = (
        peer.gateway_export_api_key.strip()
        if peer.gateway_export_api_key
        else _resolve_local_gateway_api_key()
    )
    fallback = event_at or datetime.now(UTC)
    indexed = 0
    for asset_type in AssetTypeEnum:
        try:
            docs = await fetch_gateway_export_list(
                http,
                peer,
                asset_type,
                api_key=api_key,
            )
        except httpx.HTTPError as exc:
            logger.error(
                "bootstrap gateway export failed for {} {}: {}",
                peer.name,
                asset_type.value,
                exc,
            )
            continue
        indexed += _index_export_docs(
            indexer,
            peer,
            asset_type,
            docs,
            fallback_event_at=fallback,
        )
    return indexed


async def bootstrap_peer_sync_list(
    http: httpx.AsyncClient,
    peer: PeerInfo,
    indexer: FederatedAssetIndexer,
    *,
    event_at: datetime | None = None,
) -> int:
    """Pull peer metadata from peer sync ``/webhook/list-*`` (OpenSearch)."""
    fallback = event_at or datetime.now(UTC)
    indexed = 0
    for asset_type in AssetTypeEnum:
        try:
            docs = await fetch_peer_sync_list(http, peer, asset_type)
        except httpx.HTTPError as exc:
            logger.error(
                "bootstrap peer sync export failed for {} {}: {}",
                peer.name,
                asset_type.value,
                exc,
            )
            continue
        indexed += _index_export_docs(
            indexer,
            peer,
            asset_type,
            docs,
            fallback_event_at=fallback,
        )
    return indexed


def _local_export_peer(config: FederationConfig) -> PeerInfo:
    return PeerInfo(
        name=config.site.name,
        fqdn=config.site.fqdn,
        display_name=config.site.display_name,
        gateway_api_base=config.gateway_api_base,
        sync_service_url=config.sync_service_url,
    )


async def bootstrap_local_site(
    http: httpx.AsyncClient,
    config: FederationConfig,
    indexer: FederatedAssetIndexer,
    *,
    event_at: datetime | None = None,
) -> int:
    peer = _local_export_peer(config)
    logger.info("Bootstrapping local public metadata from {}", peer.gateway_api_base)
    return await bootstrap_gateway_exports(http, peer, indexer, event_at=event_at)


async def bootstrap_all_peers(
    config: FederationConfig,
    http: httpx.AsyncClient,
    indexer: FederatedAssetIndexer,
    *,
    event_at: datetime | None = None,
) -> int:
    total = 0
    for peer in config.peers:
        logger.info(
            "Bootstrapping peer {} from sync {}",
            peer.name,
            peer.sync_service_url,
        )
        total += await bootstrap_peer_sync_list(
            http,
            peer,
            indexer,
            event_at=event_at,
        )
    return total


def peer_by_name(config: FederationConfig, site_name: str) -> PeerInfo | None:
    for peer in config.peers:
        if site_name in (peer.name, peer.fqdn):
            return peer
    return None


async def backfill_peer_on_hello(
    http: httpx.AsyncClient,
    peer: PeerInfo,
    indexer: FederatedAssetIndexer,
    *,
    event_at: datetime | None = None,
) -> int:
    """Pull a registering peer's fed-* docs via their sync list API."""
    logger.info(
        "site-hello backfill: pulling sync list for {} from {}",
        peer.name,
        peer.sync_service_url,
    )
    return await bootstrap_peer_sync_list(http, peer, indexer, event_at=event_at)


def _site_hello_payload(config: FederationConfig) -> SiteHelloWebhook:
    return SiteHelloWebhook(
        site_name=site_name_for_federation(config.site),
        fqdn=config.site.fqdn,
        display_name=config.site.display_name,
        sync_service_url=config.sync_service_url,
        timestamp=datetime.now(UTC),
    )


async def push_site_hello_to_peer(
    http: httpx.AsyncClient,
    peer: PeerInfo,
    config: FederationConfig,
) -> dict:
    url = peer_webhook_url(peer, SITE_HELLO_PATH)
    body = _site_hello_payload(config).model_dump(mode="json")
    resp = await peer_request(
        http,
        "POST",
        url,
        ca_cert_path=peer.ca_cert_path,
        json=body,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        msg = f"expected dict response from site-hello, got {type(data).__name__}"
        raise TypeError(msg)
    return data


async def register_with_peers(
    http: httpx.AsyncClient,
    config: FederationConfig,
) -> None:
    for peer in config.peers:
        try:
            result = await push_site_hello_to_peer(http, peer, config)
        except httpx.HTTPError as exc:
            logger.error("site-hello to {} failed: {}", peer.name, exc)
            continue
        if result.get("status") != "registered":
            logger.error(
                "site-hello to {} unexpected response: {}",
                peer.name,
                result,
            )


async def run_bootstrap(
    config: FederationConfig,
    http: httpx.AsyncClient,
    indexer: FederatedAssetIndexer,
    *,
    event_at: datetime | None = None,
) -> None:
    """Backfill OpenSearch from gateway export lists, then register with peers.

    Post-save signals only cover new changes; existing public assets must be
    pulled from ``/federation/export/{datasets,captures}/`` on start.
    """
    at = event_at or datetime.now(UTC)
    await ensure_local_export_api_key(http, str(config.gateway_api_base))
    local_count = await bootstrap_local_site(http, config, indexer, event_at=at)
    peer_count = await bootstrap_all_peers(config, http, indexer, event_at=at)
    logger.info(
        "Bootstrap indexed {} local and {} peer export document(s)",
        local_count,
        peer_count,
    )
    await register_with_peers(http, config)
