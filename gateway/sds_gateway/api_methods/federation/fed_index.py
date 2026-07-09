"""Write local site documents into fed-* OpenSearch indices."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from opensearchpy import OpenSearch
from sds_gateway.api_methods.models import ItemType

_EVENT_DELETED = "deleted"
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
        event_type: str,
        event_at: datetime,
        site_name: str,
        item_type: ItemType,
        uuid: UUID,
        body: dict[str, Any],
    ) -> None:
        index_name = index_for_item_type(item_type)
        doc_id = federated_doc_id(site_name, uuid)
        event_iso = event_at.isoformat()

        if event_type == _EVENT_DELETED:
            tombstone = {
                "is_federated_deleted": True,
                "federation_event_at": event_iso,
            }
            upsert_body = {**body, **tombstone}
            self._client.update(
                index=index_name,
                id=doc_id,
                body={"doc": tombstone, "upsert": upsert_body},
                refresh="wait_for",
            )
            return

        doc = {
            **body,
            "is_federated_deleted": False,
            "federation_event_at": event_iso,
        }
        self._client.index(
            index=index_name,
            id=doc_id,
            body=doc,
            refresh="wait_for",
        )
