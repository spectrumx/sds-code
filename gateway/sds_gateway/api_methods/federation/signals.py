"""Django signals that publish federation Redis events."""

from __future__ import annotations

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from loguru import logger as log

from sds_gateway.api_methods.federation.availability import is_federation_operational
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


def _skip_signal() -> bool:
    if not getattr(settings, "FEDERATION_EVENTS_ENABLED", False):
        log.debug(
            "FEDERATION_EVENTS_ENABLED is False, skipping federation signal",
        )
        return True

    if not is_federation_operational():
        log.debug("Federation not operational, skipping signal")
        return True

    return False


@receiver(post_save, sender=Dataset)
def federation_dataset_changed(
    sender: type[Dataset],
    instance: Dataset,
    created: bool,  # noqa: FBT001
    **kwargs,
) -> None:
    if _skip_signal():
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
    created: bool,  # noqa: FBT001
    **kwargs,
) -> None:
    if _skip_signal():
        return

    exportable = is_federation_exportable_capture(instance)
    publish_federation_event(
        event_type=_event_type(created=created, exportable=exportable),
        item_type=ItemType.CAPTURE,
        uuid=instance.uuid,
        timestamp=instance.updated_at,
    )
