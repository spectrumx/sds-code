"""Cached sync registry capabilities for staff UI gating."""

from __future__ import annotations

import time
from typing import Any

from django.conf import settings

from sds_gateway.api_methods.federation.sync_client import FederationSyncClient
from sds_gateway.api_methods.federation.sync_client import SyncUnavailableError

_CACHE_TTL_SECONDS = 5.0
_cache: dict[str, Any] | None = None
_cache_at: float = 0.0


def registry_sync_capabilities() -> dict[str, Any] | None:
    global _cache, _cache_at
    if getattr(settings, "FEDERATION_REGISTRY_BACKEND", "gateway") != "sync":
        return None
    now = time.monotonic()
    if _cache is not None and (now - _cache_at) < _CACHE_TTL_SECONDS:
        return _cache
    try:
        _cache = FederationSyncClient.from_settings().capabilities()
    except SyncUnavailableError:
        _cache = {"publish_enabled": False, "key_configured": False}
    _cache_at = now
    return _cache
