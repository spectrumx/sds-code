"""Read federated documents from shared fed-* OpenSearch indices."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

from opensearchpy.exceptions import NotFoundError

from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import FederatedCaptureDoc
from sds_federation.schemas.webhooks import FederatedDatasetDoc
from sds_federation.schemas.webhooks import asset_doc_class
from sds_federation.services.fed_index import doc_id

if TYPE_CHECKING:
    from opensearchpy import OpenSearch

_FEDERATION_META_KEYS = frozenset(
    {"is_federated_deleted", "federation_event_at"},
)


def _strip_federation_meta(source: dict) -> dict:
    return {key: value for key, value in source.items() if key not in _FEDERATION_META_KEYS}


def load_federated_asset(
    client: OpenSearch,
    *,
    site_name: str,
    uuid: UUID,
    asset_type: AssetTypeEnum,
) -> FederatedDatasetDoc | FederatedCaptureDoc | None:
    """Return the indexed document for a site asset, or None if missing."""

    def _get() -> dict | None:
        try:
            response = client.get(index=asset_type.index_name, id=doc_id(site_name, uuid))
        except NotFoundError:
            return None
        source = response.get("_source")
        if not isinstance(source, dict):
            return None
        return source

    source = _get()
    if source is None:
        return None
    doc_class = asset_doc_class(asset_type)
    return doc_class.model_validate(_strip_federation_meta(source))


async def aload_federated_asset(
    client: OpenSearch,
    *,
    site_name: str,
    uuid: UUID,
    asset_type: AssetTypeEnum,
) -> FederatedDatasetDoc | FederatedCaptureDoc | None:
    return await asyncio.to_thread(
        load_federated_asset,
        client,
        site_name=site_name,
        uuid=uuid,
        asset_type=asset_type,
    )
