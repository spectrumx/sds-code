from datetime import datetime
from uuid import UUID

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError

from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import FederatedCaptureDoc
from sds_federation.schemas.webhooks import FederatedDatasetDoc


def doc_id(site_name: str, uuid: UUID) -> str:
    return f"{site_name}:{uuid}"


def _parse_event_at(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value)
    return None


class FederatedAssetIndexer:
    def __init__(self, client: OpenSearch) -> None:
        self._client = client
        # Process-local cache; OpenSearch federation_event_at is authoritative.
        self._last_event: dict[str, datetime] = {}

    def _stored_event_at(self, index_name: str, _id: str) -> datetime | None:
        try:
            doc = self._client.get(index=index_name, id=_id)
        except NotFoundError:
            return None
        source = doc.get("_source") or {}
        return _parse_event_at(source.get("federation_event_at"))

    def _is_stale(
        self,
        site_name: str,
        uuid: UUID,
        event_at: datetime,
        *,
        index_name: str,
    ) -> bool:
        key = doc_id(site_name, uuid)
        prev = self._last_event.get(key)
        if prev is None:
            prev = self._stored_event_at(index_name, key)
            if prev is not None:
                self._last_event[key] = prev
        return bool(prev is not None and event_at <= prev)

    def _mark_applied(self, site_name: str, uuid: UUID, event_at: datetime) -> None:
        self._last_event[doc_id(site_name, uuid)] = event_at

    def apply_asset_event(
        self,
        *,
        event_at: datetime,
        site_name: str,
        asset: FederatedDatasetDoc | FederatedCaptureDoc | None,
        asset_type: AssetTypeEnum,
    ) -> None:
        if asset is None:
            kind = asset_type.value
            msg = f"{kind} body required for {kind}-updated webhook"
            raise ValueError(msg)

        if asset.site_name != site_name:
            raise ValueError(f"site_name must match {asset_type.value}.site_name")

        if self._is_stale(
            site_name,
            asset.uuid,
            event_at,
            index_name=asset_type.index_name,
        ):
            return

        _id = doc_id(site_name, asset.uuid)
        body = asset.model_dump(mode="json")
        body["federation_event_at"] = event_at.isoformat()
        self._client.index(
            index=asset_type.index_name,
            id=_id,
            body=body,
            refresh="wait_for",
        )

        self._mark_applied(site_name, asset.uuid, event_at)
