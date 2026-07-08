"""Federated metadata search (RFC GET /search/datasets, /search/captures)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Query
from fastapi import Request
from opensearchpy import OpenSearch

from sds_federation.services.fed_search import search_federated_captures
from sds_federation.services.fed_search import search_federated_datasets

search_index_router = APIRouter(tags=["search"])


def _opensearch_client(request: Request) -> OpenSearch:
    client = getattr(
        request.app.state,
        "opensearch_client",
        None,
    )
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="OpenSearch client not ready",
        )
    return client


def _parse_metadata_filters(raw: str | None) -> list[dict[str, Any]] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as err:
        raise HTTPException(
            status_code=400,
            detail="'metadata_filters' must be valid JSON",
        ) from err
    if not isinstance(parsed, list):
        raise HTTPException(
            status_code=400,
            detail="'metadata_filters' must be a JSON list",
        )
    return parsed


@search_index_router.get("/search/datasets")
async def search_datasets(
    request: Request,
    q: str | None = Query(default=None, description="Free-text search"),
    site: str | None = Query(
        default="*",
        description="Peer site FQDN (federation.toml fqdn) or *",
    ),
    metadata_filters: str | None = Query(
        default=None,
        description="JSON list of metadata filter objects",
    ),
) -> dict[str, Any]:
    client = _opensearch_client(request)
    filters = _parse_metadata_filters(metadata_filters)
    try:
        return search_federated_datasets(
            client,
            q=q,
            site=site,
            metadata_filters=filters,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@search_index_router.get("/search/captures")
async def search_captures(
    request: Request,
    q: str | None = Query(default=None, description="Free-text search"),
    site: str | None = Query(
        default="*",
        description="Peer site FQDN (federation.toml fqdn) or *",
    ),
    capture_type: str | None = Query(default=None),
    metadata_filters: str | None = Query(
        default=None,
        description="JSON list of metadata filter objects",
    ),
) -> dict[str, Any]:
    client = _opensearch_client(request)
    filters = _parse_metadata_filters(metadata_filters)
    try:
        return search_federated_captures(
            client,
            q=q,
            site=site,
            capture_type=capture_type,
            metadata_filters=filters,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
