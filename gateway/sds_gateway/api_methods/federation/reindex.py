"""Reindex federation export documents and notify sync."""

from __future__ import annotations

from collections.abc import Iterable

from django.db import transaction
from loguru import logger as log

from sds_gateway.api_methods.federation.availability import is_federation_operational
from sds_gateway.api_methods.federation.compile_federated_data import (
    capture_in_published_dataset,
)
from sds_gateway.api_methods.federation.compile_federated_data import compile_federated_doc
from sds_gateway.api_methods.federation.compile_federated_data import fed_doc_exists
from sds_gateway.api_methods.federation.compile_federated_data import (
    get_federated_export_doc_by_uuid,
)
from sds_gateway.api_methods.federation.compile_federated_data import federation_site_name
from sds_gateway.api_methods.federation.events import publish_federation_event
from sds_gateway.api_methods.federation.fed_index import LocalFederatedIndexer
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client


def reindex_federated_asset(
    instance: Dataset | Capture,
    item_type: ItemType,
) -> None:
    if not is_federation_operational():
        log.debug("Federation indexing disabled; skipping reindex")
        return

    site_name = federation_site_name()
    timestamp = instance.updated_at
    body = compile_federated_doc(instance)

    try:
        LocalFederatedIndexer(get_opensearch_client()).apply_local_event(
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
        item_type=item_type,
        uuid=instance.uuid,
        timestamp=timestamp,
    )


def schedule_federation_dataset_reindex(dataset: Dataset) -> None:
    """Run dataset (+ exportable member captures) reindex after transaction commit."""
    dataset_pk = dataset.pk

    def _on_commit() -> None:
        try:
            fresh = Dataset.objects.get(pk=dataset_pk)
        except Dataset.DoesNotExist:
            return
        try:
            if not dataset_needs_federation_reindex(fresh):
                return
            reindex_federated_asset(fresh, ItemType.DATASET)
            if fresh.is_deleted or not fresh.is_federation_exportable():
                return
            for capture in fresh.captures.filter(is_deleted=False):
                if capture_needs_federation_reindex(capture):
                    reindex_federated_asset(capture, ItemType.CAPTURE)
        except Exception as exc:  # noqa: BLE001
            log.warning("Federation dataset reindex on commit failed: {}", exc)

    transaction.on_commit(_on_commit, robust=True)


def schedule_federation_capture_reindex(capture: Capture) -> None:
    """Run capture reindex after transaction commit."""
    capture_pk = capture.pk

    def _on_commit() -> None:
        try:
            fresh = Capture.objects.get(pk=capture_pk)
        except Capture.DoesNotExist:
            return
        try:
            if not capture_needs_federation_reindex(fresh):
                return
            reindex_federated_asset(fresh, ItemType.CAPTURE)
        except Exception as exc:  # noqa: BLE001
            log.warning("Federation capture reindex on commit failed: {}", exc)

    transaction.on_commit(_on_commit, robust=True)


def reindex_captures_after_dataset_unlink(capture_pks: Iterable[int]) -> None:
    """Reindex captures unlinked from a dataset after transaction commit."""
    pks = list(capture_pks)
    if not pks:
        return

    def _on_commit() -> None:
        try:
            for capture in Capture.objects.filter(pk__in=pks):
                if capture_needs_federation_reindex(capture):
                    reindex_federated_asset(capture, ItemType.CAPTURE)
        except Exception as exc:  # noqa: BLE001
            log.warning("Federation capture unlink reindex on commit failed: {}", exc)

    transaction.on_commit(_on_commit, robust=True)


def _fed_doc_shows_is_deleted(
    instance: Dataset | Capture,
    item_type: ItemType,
) -> bool:
    site_name = federation_site_name()
    if not site_name:
        return False
    source = get_federated_export_doc_by_uuid(
        asset_type=item_type,
        asset_uuid=instance.uuid,
        site_name=site_name,
    )
    if source is None:
        return False
    return source.get("is_deleted") is True


def dataset_needs_federation_reindex(dataset: Dataset) -> bool:
    if dataset.is_deleted:
        return not _fed_doc_shows_is_deleted(dataset, ItemType.DATASET) and fed_doc_exists(
            asset_type=ItemType.DATASET,
            site_name=federation_site_name(),
            instance=dataset,
        )
    if dataset.is_federation_exportable():
        return True
    site_name = federation_site_name()
    if not site_name:
        return False
    return fed_doc_exists(
        asset_type=ItemType.DATASET,
        site_name=site_name,
        instance=dataset,
    )


def capture_needs_federation_reindex(capture: Capture) -> bool:
    if capture.is_deleted:
        return not _fed_doc_shows_is_deleted(capture, ItemType.CAPTURE) and fed_doc_exists(
            asset_type=ItemType.CAPTURE,
            site_name=federation_site_name(),
            instance=capture,
        )
    if capture_in_published_dataset(capture):
        return True
    site_name = federation_site_name()
    if not site_name:
        return False
    return fed_doc_exists(
        asset_type=ItemType.CAPTURE,
        site_name=site_name,
        instance=capture,
    )
