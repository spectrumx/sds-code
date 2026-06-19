from datetime import datetime
from uuid import UUID

from opensearchpy import OpenSearch

from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import FederatedCaptureDoc
from sds_federation.schemas.webhooks import FederatedDatasetDoc
from sds_federation.schemas.webhooks import FederationEventType


def doc_id(site_name: str, uuid: UUID) -> str:
    return f"{site_name}:{uuid}"


class FederatedAssetIndexer:
    def __init__(self, client: OpenSearch) -> None:
        self._client = client
        # MVP dedupe: production may store last_event_at on the OS doc
        self._last_event: dict[str, datetime] = {}

    def _is_stale(self, site_name: str, uuid: UUID, event_at: datetime) -> bool:
        key = doc_id(site_name, uuid)
        prev = self._last_event.get(key)
        return bool(prev is not None and event_at <= prev)

    def _mark_applied(self, site_name: str, uuid: UUID, event_at: datetime) -> None:
        self._last_event[doc_id(site_name, uuid)] = event_at

    def apply_asset_event(
        self,
        *,
        event_type: FederationEventType,
        event_at: datetime,
        site_name: str,
        asset: FederatedDatasetDoc | FederatedCaptureDoc | None,
        asset_type: AssetTypeEnum,
    ) -> None:
        if asset is None:
            kind = asset_type.value
            msg = f"{kind} body required for {kind}-updated webhook"
            raise ValueError(msg)

        # TODO: validate asset type matches body for a given asset type

        if asset.site_name != site_name:
            raise ValueError(f"site_name must match {asset_type.value}.site_name")

        if self._is_stale(site_name, asset.uuid, event_at):
            return

        _id = doc_id(site_name, asset.uuid)

        if event_type == FederationEventType.DELETED:
            self._client.update(
                index=asset_type.index_name,
                id=_id,
                body={
                    "doc": {
                        "is_federated_deleted": True,
                        "federation_event_at": event_at.isoformat(),
                    },
                    "doc_as_upsert": True,
                },
                refresh="wait_for",
            )
        else:
            body = asset.model_dump(mode="json")
            body["is_federated_deleted"] = False
            body["federation_event_at"] = event_at.isoformat()
            self._client.index(
                index=asset_type.index_name,
                id=_id,
                body=body,
                refresh="wait_for",
            )

        self._mark_applied(site_name, asset.uuid, event_at)
