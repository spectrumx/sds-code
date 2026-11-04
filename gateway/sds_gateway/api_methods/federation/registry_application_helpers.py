"""Shared registry application helpers (no sync HTTP)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from sds_gateway.api_methods.models import RegistryApplicationStatus

if TYPE_CHECKING:
    from sds_gateway.api_methods.models import RegistryApplication

VERIFYABLE_STATUSES = frozenset(
    {
        RegistryApplicationStatus.PENDING_VERIFICATION.value,
        RegistryApplicationStatus.VERIFICATION_FAILED.value,
    },
)


def backfill_urls_from_well_known(
    application: RegistryApplication,
    well_known: dict[str, Any],
) -> list[str]:
    updated: list[str] = []
    for field, key in (
        ("gateway_api_base", "gateway_api_base"),
        ("sync_service_url", "sync_service_url"),
    ):
        if getattr(application, field):
            continue
        value = well_known.get(key)
        if isinstance(value, str) and value.strip():
            setattr(application, field, value.strip())
            updated.append(field)
    return updated
