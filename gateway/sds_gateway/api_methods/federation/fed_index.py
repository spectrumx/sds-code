"""Write local site documents into fed-* OpenSearch indices."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from opensearchpy import OpenSearch
from sds_gateway.api_methods.models import ItemType

FED_DATASETS_INDEX = "fed-datasets"
FED_CAPTURES_INDEX = "fed-captures"


def federated_doc_id(site_name: str, uuid: UUID) -> str:
    return f"{site_name}:{uuid}"


def index_for_item_type(item_type: ItemType) -> str:
    if item_type == ItemType.DATASET:
        return FED_DATASETS_INDEX
    if item_type == ItemType.CAPTURE:
        return FED_CAPTURES_INDEX
    msg = f"unsupported federation item type: {item_type}"
    raise ValueError(msg)


class LocalFederatedIndexer:
    """Index this site's public federation export shape into shared fed-* indices."""

    def __init__(self, client: OpenSearch) -> None:
        self._client = client

    def apply_local_event(
        self,
        *,
        event_at: datetime,
        site_name: str,
        item_type: ItemType,
        uuid: UUID,
        body: dict[str, Any],
    ) -> None:
        index_name = index_for_item_type(item_type)
        doc_id = federated_doc_id(site_name, uuid)
        doc = {
            **body,
            "federation_event_at": event_at.isoformat(),
        }
        self._client.index(
            index=index_name,
            id=doc_id,
            body=doc,
            refresh="wait_for",
        )
