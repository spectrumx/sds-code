"""Index local fed-* docs on save, then notify sync via Redis."""

from __future__ import annotations

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from loguru import logger as log

from sds_gateway.api_methods.federation.compile_federated_data import (
    capture_in_other_published_datasets,
)
from sds_gateway.api_methods.federation.compile_federated_data import (
    capture_in_published_dataset,
)
from sds_gateway.api_methods.federation.compile_federated_data import (
    compile_federated_doc,
)
from sds_gateway.api_methods.federation.compile_federated_data import (
    fed_doc_exists,
)
from sds_gateway.api_methods.federation.compile_federated_data import (
    fed_doc_is_tombstoned,
)
from sds_gateway.api_methods.federation.compile_federated_data import (
    federation_site_name,
)
from sds_gateway.api_methods.federation.events import FederationEventType
from sds_gateway.api_methods.federation.events import publish_federation_event
from sds_gateway.api_methods.federation.fed_index import LocalFederatedIndexer
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client


def _federation_indexing_enabled() -> bool:
    if not getattr(settings, "FEDERATION_ENABLED", False):
        return False
    return bool(federation_site_name())


def _event_type(*, created: bool, deleted: bool) -> FederationEventType:
    if deleted:
        return FederationEventType.DELETED
    if created:
        return FederationEventType.CREATED
    return FederationEventType.UPDATED


def _federation_created_flag(
    instance: Dataset | Capture,
    item_type: ItemType,
) -> bool:
    site_name = federation_site_name()
    if not fed_doc_exists(
        asset_type=item_type,
        site_name=site_name,
        instance=instance,
    ):
        return True
    return fed_doc_is_tombstoned(
        asset_type=item_type,
        site_name=site_name,
        instance=instance,
    )


def _ignore_stale_deleted_update(
    instance: Dataset | Capture,
    item_type: ItemType,
) -> bool:
    if not instance.is_deleted:
        return False
    site_name = federation_site_name()
    if not fed_doc_exists(
        asset_type=item_type,
        site_name=site_name,
        instance=instance,
    ):
        return True
    return fed_doc_is_tombstoned(
        asset_type=item_type,
        site_name=site_name,
        instance=instance,
    )


def _index_and_notify(
    *,
    instance: Dataset | Capture,
    item_type: ItemType,
    created: bool,
    deleted: bool,
) -> None:
    if not _federation_indexing_enabled():
        log.debug("Federation indexing disabled; skipping signal")
        return

    site_name = federation_site_name()
    event_type = _event_type(created=created, deleted=deleted)
    timestamp = instance.updated_at
    body = compile_federated_doc(instance)

    try:
        LocalFederatedIndexer(get_opensearch_client()).apply_local_event(
            event_type=str(event_type),
            event_at=timestamp,
            site_name=site_name,
            item_type=item_type,
            uuid=instance.uuid,
            body=body,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Federation OpenSearch index failed: {}", exc)
        return

    publish_federation_event(
        event_type=event_type,
        item_type=item_type,
        uuid=instance.uuid,
        timestamp=timestamp,
    )


def _tombstone_federated_if_exists(
    instance: Dataset | Capture,
    item_type: ItemType,
) -> None:
    site_name = federation_site_name()
    if not fed_doc_exists(
        asset_type=item_type,
        site_name=site_name,
        instance=instance,
    ):
        return
    if fed_doc_is_tombstoned(
        asset_type=item_type,
        site_name=site_name,
        instance=instance,
    ):
        return
    _index_and_notify(
        instance=instance,
        item_type=item_type,
        created=False,
        deleted=True,
    )


def _upsert_federated(instance: Dataset | Capture, item_type: ItemType) -> None:
    created = _federation_created_flag(instance, item_type)
    _index_and_notify(
        instance=instance,
        item_type=item_type,
        created=created,
        deleted=False,
    )


def _maybe_tombstone_capture_after_dataset_change(
    capture: Capture,
    *,
    dataset: Dataset,
) -> None:
    if _ignore_stale_deleted_update(capture, ItemType.CAPTURE):
        return
    if capture_in_other_published_datasets(
        capture,
        exclude_dataset_id=dataset.uuid,
    ):
        return
    _tombstone_federated_if_exists(capture, ItemType.CAPTURE)


def _sync_published_captures_for_dataset(dataset: Dataset) -> None:
    for capture in dataset.captures.filter(is_deleted=False):
        if not capture_in_published_dataset(capture):
            continue
        if _ignore_stale_deleted_update(capture, ItemType.CAPTURE):
            continue
        _upsert_federated(capture, ItemType.CAPTURE)


@receiver(post_save, sender=Dataset)
def federation_dataset_changed(
    sender: type[Dataset],
    instance: Dataset,
    created: bool,  # noqa: FBT001
    **kwargs,
) -> None:
    if not _federation_indexing_enabled():
        return
    if _ignore_stale_deleted_update(instance, ItemType.DATASET):
        return

    if instance.is_deleted:
        _tombstone_federated_if_exists(instance, ItemType.DATASET)
        for capture in instance.captures.all():
            _maybe_tombstone_capture_after_dataset_change(capture, dataset=instance)
        return

    if not instance.is_federation_exportable():
        return

    _upsert_federated(instance, ItemType.DATASET)
    _sync_published_captures_for_dataset(instance)


@receiver(post_save, sender=Capture)
def federation_capture_changed(
    sender: type[Capture],
    instance: Capture,
    **kwargs,
) -> None:
    if not _federation_indexing_enabled():
        return
    if _ignore_stale_deleted_update(instance, ItemType.CAPTURE):
        return

    if instance.is_deleted:
        _tombstone_federated_if_exists(instance, ItemType.CAPTURE)
        return

    if not capture_in_published_dataset(instance):
        return

    _upsert_federated(instance, ItemType.CAPTURE)
