"""Index local fed-* docs on save, then notify sync via Redis."""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from sds_gateway.api_methods.federation.availability import is_federation_operational
from sds_gateway.api_methods.federation.reindex import capture_needs_federation_reindex
from sds_gateway.api_methods.federation.reindex import dataset_needs_federation_reindex
from sds_gateway.api_methods.federation.reindex import reindex_federated_asset
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType


def _reindex_dataset_captures(dataset: Dataset) -> None:
    for capture in dataset.captures.filter(is_deleted=False):
        if capture_needs_federation_reindex(capture):
            reindex_federated_asset(capture, ItemType.CAPTURE)


@receiver(post_save, sender=Dataset)
def federation_dataset_changed(
    sender: type[Dataset],
    instance: Dataset,
    created: bool,  # noqa: FBT001, ARG001
    **kwargs,
) -> None:
    if not is_federation_operational():
        return
    if not dataset_needs_federation_reindex(instance):
        return

    reindex_federated_asset(instance, ItemType.DATASET)
    if instance.is_deleted or not instance.is_federation_exportable():
        return
    _reindex_dataset_captures(instance)


@receiver(post_save, sender=Capture)
def federation_capture_changed(
    sender: type[Capture],
    instance: Capture,
    **kwargs,
) -> None:
    if not is_federation_operational():
        return
    if not capture_needs_federation_reindex(instance):
        return
    reindex_federated_asset(instance, ItemType.CAPTURE)
