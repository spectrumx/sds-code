"""Publish federation change notifications to Redis."""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any

from django.conf import settings
from loguru import logger as log

from sds_gateway.api_methods.federation.availability import is_federation_operational
from sds_gateway.api_methods.tasks import get_redis_client

if TYPE_CHECKING:
    from uuid import UUID

    from sds_gateway.api_methods.models import ItemType


def publish_federation_event(
    *,
    item_type: ItemType,
    uuid: UUID,
    timestamp: datetime | None = None,
) -> None:
    """Notify the local federation sync service via Redis pub/sub."""
    if not is_federation_operational():
        log.debug("Federation not operational, skipping Redis publish")
        return
    channel = settings.FEDERATION_EVENTS_CHANNEL
    payload: dict[str, Any] = {
        "item_type": item_type.value,
        "uuid": str(uuid),
        "timestamp": (timestamp or datetime.now(UTC)).isoformat(),
    }
    try:
        client = get_redis_client()
        client.publish(channel, json.dumps(payload))
    except Exception as err:  # noqa: BLE001
        log.warning(f"Failed to publish federation event: {err}")
