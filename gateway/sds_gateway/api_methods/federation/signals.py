"""Django signals that publish federation Redis events."""

from __future__ import annotations

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from loguru import logger as log

from sds_gateway.api_methods.federation.events import publish_federation_event
from sds_gateway.api_methods.helpers.compile_federated_data import (
    is_federation_exportable_capture,
)
from sds_gateway.api_methods.helpers.compile_federated_data import (
    is_federation_exportable_dataset,
)
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType


def _event_type(*, created: bool, exportable: bool) -> str:
    if not exportable:
        return "deleted"
    return "created" if created else "updated"


@receiver(post_save, sender=Dataset)
def federation_dataset_changed(
    sender: type[Dataset],
    instance: Dataset,
    created: bool,
    **kwargs,
) -> None:
    if not getattr(settings, "FEDERATION_EVENTS_ENABLED", True):
        log.debug(
            "FEDERATION_EVENTS_ENABLED is False, "
            "skipping federation dataset changed signal",
        )
        return

    exportable = is_federation_exportable_dataset(instance)
    publish_federation_event(
        event_type=_event_type(created=created, exportable=exportable),
        item_type=ItemType.DATASET,
        uuid=instance.uuid,
        timestamp=instance.updated_at,
    )


@receiver(post_save, sender=Capture)
def federation_capture_changed(
    sender: type[Capture],
    instance: Capture,
    created: bool,
    **kwargs,
) -> None:
    if not getattr(settings, "FEDERATION_EVENTS_ENABLED", True):
        log.debug(
            "FEDERATION_EVENTS_ENABLED is False, "
            "skipping federation capture changed signal",
        )
        return

    exportable = is_federation_exportable_capture(instance)
    publish_federation_event(
        event_type=_event_type(created=created, exportable=exportable),
        item_type=ItemType.CAPTURE,
        uuid=instance.uuid,
        timestamp=instance.updated_at,
    )
