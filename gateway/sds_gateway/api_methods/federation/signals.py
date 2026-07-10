"""Index local fed-* docs on save, then notify sync via Redis."""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from sds_gateway.api_methods.federation.availability import is_federation_operational
from sds_gateway.api_methods.federation.reindex import schedule_federation_capture_reindex
from sds_gateway.api_methods.federation.reindex import schedule_federation_dataset_reindex
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset


@receiver(post_save, sender=Dataset)
def federation_dataset_changed(
    sender: type[Dataset],
    instance: Dataset,
    created: bool,  # noqa: FBT001, ARG001
    **kwargs,
) -> None:
    if not is_federation_operational():
        return
    schedule_federation_dataset_reindex(instance)


@receiver(post_save, sender=Capture)
def federation_capture_changed(
    sender: type[Capture],
    instance: Capture,
    **kwargs,
) -> None:
    if not is_federation_operational():
        return
    schedule_federation_capture_reindex(instance)
