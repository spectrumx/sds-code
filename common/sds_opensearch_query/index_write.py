"""Shared fed-* OpenSearch document id and index write helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from opensearchpy import OpenSearch

FED_DATASETS_INDEX = "fed-datasets"
FED_CAPTURES_INDEX = "fed-captures"


def federated_doc_id(site_name: str, uuid: UUID | str) -> str:
    """Stable OpenSearch ``_id`` for a site-owned federated asset."""
    return f"{site_name}:{uuid}"


def index_federated_document(
    client: OpenSearch,
    *,
    index_name: str,
    site_name: str,
    uuid: UUID,
    body: dict[str, Any],
    event_at: datetime,
    refresh: str | bool = "wait_for",
) -> str:
    """Index a federated document and stamp ``federation_event_at``.

    Returns the document id written.
    """
    doc_id = federated_doc_id(site_name, uuid)
    doc = {
        **body,
        "federation_event_at": event_at.isoformat(),
    }
    client.index(
        index=index_name,
        id=doc_id,
        body=doc,
        refresh=refresh,
    )
    return doc_id
