"""Federation operational status: config, sync health, Redis, sync API key."""

from __future__ import annotations

import ipaddress
import json
import time
import urllib.error
import urllib.request
from typing import Any

from config.settings.base import FEDERATION_EXPORT_ALLOWED_CIDRS_DEFAULT
from config.settings.base import _parse_cidrs
from django.conf import settings
from django.db import connection
from django.db.utils import DatabaseError
from loguru import logger as log

from sds_gateway.api_methods.models import KeySources
from sds_gateway.api_methods.tasks import get_redis_client
from sds_gateway.users.models import UserAPIKey

_HTTP_OK = 200
_RECHECK_INTERVAL_SECONDS = 60.0
_last_evaluated_at: float = 0.0
_cached_operational: bool = False
_cached_reason: str = "not evaluated"


def _setting(name: str, *, default: Any = None) -> Any:
    return getattr(settings, name, default)


def _export_allowed_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Networks from settings (parsed at startup); tests may override with strings."""
    raw = _setting("FEDERATION_EXPORT_ALLOWED_CIDRS", default=[])
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for item in raw:
        if isinstance(item, (ipaddress.IPv4Network, ipaddress.IPv6Network)):
            networks.append(item)
            continue
        text = str(item).strip()
        if not text:
            continue
        networks.append(ipaddress.ip_network(text, strict=False))
    if not networks:
        networks = _parse_cidrs(FEDERATION_EXPORT_ALLOWED_CIDRS_DEFAULT)
    return networks


def federation_client_ip(request) -> str | None:
    """Client IP for export access control (direct internal connections only)."""
    remote = request.META.get("REMOTE_ADDR")
    if remote:
        return str(remote).strip()
    return None


def is_client_ip_allowed_for_federation_export(request) -> bool:
    cidrs = _export_allowed_networks()
    if not cidrs:
        return False
    client_ip = federation_client_ip(request)
    if not client_ip:
        return False
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    return any(addr in network for network in cidrs)


def _sync_health_ok() -> tuple[bool, str]:  # noqa: C901, PLR0911
    if _setting("FEDERATION_SKIP_SYNC_HEALTH_PROBE", default=False):
        return True, "health probe skipped"
    url = (_setting("FEDERATION_SYNC_HEALTH_URL") or "").strip()
    if not url:
        return False, "FEDERATION_SYNC_HEALTH_URL is not set"
    if not url.startswith(("http://", "https://")):
        return False, "FEDERATION_SYNC_HEALTH_URL must be http(s)"
    timeout = float(
        _setting("FEDERATION_SYNC_HEALTH_PROBE_TIMEOUT", default=2.0),
    )
    request = urllib.request.Request(url, method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            if response.status != _HTTP_OK:
                return False, f"sync health returned HTTP {response.status}"
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return False, f"sync health probe failed: {exc.reason}"
    except TimeoutError:
        return False, "sync health probe timed out"
    if not body.strip():
        return True, "sync health returned 200"

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return True, "sync health returned 200"

    if isinstance(payload, dict):
        if payload.get("status") == "ok":
            return True, "sync health ok"
        status_value = payload.get("status")
        return False, f"sync health status is not ok: {status_value!r}"

    return True, "sync health returned 200"


def _sync_api_key_present() -> tuple[bool, str]:
    if _setting("FEDERATION_SKIP_SYNC_API_KEY_CHECK", default=False):
        return True, "sync API key check skipped"
    exists = UserAPIKey.objects.filter(
        source=KeySources.FederationSync,
        revoked=False,
    ).exists()
    if not exists:
        return False, "no FederationSync API key in database"
    return True, "FederationSync API key present"


def _redis_ok() -> tuple[bool, str]:
    if not _setting("FEDERATION_ENABLED", default=False):
        return True, "redis not required (federation disabled)"
    if _setting("FEDERATION_SKIP_REDIS_PROBE", default=False):
        return True, "redis probe skipped"

    try:
        client = get_redis_client()
        client.ping()
    except Exception as exc:  # noqa: BLE001
        return False, f"redis ping failed: {exc}"
    return True, "redis ok"


def evaluate_federation_operational() -> tuple[bool, str]:
    if not _setting("FEDERATION_ENABLED", default=False):
        return False, "FEDERATION_ENABLED is False"

    site_name = (_setting("FEDERATION_SITE_NAME", default="") or "").strip()
    if not site_name:
        return False, "FEDERATION_SITE_NAME must be set when federation is enabled"

    for check in (_sync_api_key_present, _redis_ok, _sync_health_ok):
        ok, reason = check()
        if not ok:
            return False, reason
    return True, "federation operational"


def refresh_federation_operational_state(*, force: bool = False) -> tuple[bool, str]:
    global _cached_operational, _cached_reason, _last_evaluated_at  # noqa: PLW0603

    now = time.monotonic()
    if (
        not force
        and _last_evaluated_at
        and (now - _last_evaluated_at) < _RECHECK_INTERVAL_SECONDS
    ):
        return _cached_operational, _cached_reason

    operational, reason = evaluate_federation_operational()
    _cached_operational = operational
    _cached_reason = reason
    _last_evaluated_at = now
    settings.FEDERATION_OPERATIONAL = operational
    settings.FEDERATION_OPERATIONAL_REASON = reason
    return operational, reason


def federation_operational_db_ready() -> bool:
    """False when federation probes would hit tables that are not migrated yet."""
    if not _setting("FEDERATION_ENABLED", default=False):
        return True
    table = UserAPIKey._meta.db_table  # noqa: SLF001
    try:
        return table in connection.introspection.table_names()
    except DatabaseError:
        return False


def initialize_federation_operational_state() -> None:
    if not federation_operational_db_ready():
        settings.FEDERATION_OPERATIONAL = False
        settings.FEDERATION_OPERATIONAL_REASON = "database tables not ready"
        log.debug("Federation operational init deferred until migrations apply")
        return

    operational, reason = refresh_federation_operational_state(force=True)
    if operational:
        log.info("Federation is operational: {}", reason)
    else:
        log.warning("Federation disabled: {}", reason)


def is_federation_operational() -> bool:
    if _setting("FEDERATION_OPERATIONAL_OVERRIDE", default=None) is not None:
        return bool(_setting("FEDERATION_OPERATIONAL_OVERRIDE"))
    if not _setting("FEDERATION_ENABLED", default=False):
        return False
    operational, _reason = refresh_federation_operational_state()
    return operational
