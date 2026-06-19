"""Federation operational status: config, sync health, Redis, sync API key."""

from __future__ import annotations

import ipaddress
import json
import secrets
import time
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings
from loguru import logger as log

from sds_gateway.api_methods.models import KeySources
from sds_gateway.users.models import UserAPIKey

_RECHECK_INTERVAL_SECONDS = 60.0
_last_evaluated_at: float = 0.0
_cached_operational: bool = False
_cached_reason: str = "not evaluated"


def _setting(name: str, default: Any = None) -> Any:
    return getattr(settings, name, default)


def _parse_cidrs(raw: list[str]) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for item in raw:
        networks.append(ipaddress.ip_network(item.strip(), strict=False))
    return networks


def federation_client_ip(request) -> str | None:
    """Resolve client IP for federation export access control."""
    trust_forwarded = _setting("FEDERATION_EXPORT_TRUST_X_FORWARDED_FOR", False)
    if trust_forwarded:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    remote = request.META.get("REMOTE_ADDR")
    if remote:
        return str(remote).strip()
    return None


def is_client_ip_allowed_for_federation_export(request) -> bool:
    cidrs = _parse_cidrs(_setting("FEDERATION_EXPORT_ALLOWED_CIDRS", []))
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


def is_federation_internal_header_valid(request) -> bool:
    secret = _setting("FEDERATION_EXPORT_INTERNAL_HEADER_SECRET", "")
    if not secret:
        return True
    header_name = _setting(
        "FEDERATION_EXPORT_INTERNAL_HEADER_NAME",
        "X-SDS-Federation-Internal",
    )
    meta_key = "HTTP_" + header_name.upper().replace("-", "_")
    provided = request.META.get(meta_key, "")
    if not provided:
        return False
    return secrets.compare_digest(str(provided), str(secret))


def _sync_health_ok() -> tuple[bool, str]:
    if _setting("FEDERATION_SKIP_SYNC_HEALTH_PROBE", False):
        return True, "health probe skipped"
    url = (_setting("FEDERATION_SYNC_HEALTH_URL") or "").strip()
    if not url:
        return False, "FEDERATION_SYNC_HEALTH_URL is not set"
    timeout = float(_setting("FEDERATION_SYNC_HEALTH_PROBE_TIMEOUT", 2.0))
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                return False, f"sync health returned HTTP {response.status}"
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        return False, f"sync health probe failed: {exc.reason}"
    except TimeoutError:
        return False, "sync health probe timed out"
    if body:
        try:
            payload = json.loads(body)
            if isinstance(payload, dict) and payload.get("status") == "ok":
                return True, "sync health ok"
        except json.JSONDecodeError:
            pass
        return True, "sync health returned 200"
    return True, "sync health returned 200"


def _sync_api_key_present() -> tuple[bool, str]:
    if _setting("FEDERATION_SKIP_SYNC_API_KEY_CHECK", False):
        return True, "sync API key check skipped"
    exists = UserAPIKey.objects.filter(source=KeySources.FederationSync).exists()
    if not exists:
        return False, "no FederationSync API key in database"
    return True, "FederationSync API key present"


def _redis_ok() -> tuple[bool, str]:
    if not _setting("FEDERATION_EVENTS_ENABLED", False):
        return True, "redis not required (events disabled)"
    if _setting("FEDERATION_SKIP_REDIS_PROBE", False):
        return True, "redis probe skipped"
    from sds_gateway.api_methods.tasks import get_redis_client

    try:
        client = get_redis_client()
        client.ping()
    except Exception as exc:  # noqa: BLE001
        return False, f"redis ping failed: {exc}"
    return True, "redis ok"


def evaluate_federation_operational() -> tuple[bool, str]:
    if not _setting("FEDERATION_ENABLED", False):
        return False, "FEDERATION_ENABLED is False"

    for check in (_sync_api_key_present, _sync_health_ok, _redis_ok):
        ok, reason = check()
        if not ok:
            return False, reason
    return True, "federation operational"


def refresh_federation_operational_state(*, force: bool = False) -> tuple[bool, str]:
    global _cached_operational, _cached_reason, _last_evaluated_at

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


def initialize_federation_operational_state() -> None:
    operational, reason = refresh_federation_operational_state(force=True)
    if operational:
        log.info("Federation is operational: {}", reason)
    else:
        log.warning("Federation disabled: {}", reason)


def is_federation_operational() -> bool:
    if _setting("FEDERATION_OPERATIONAL_OVERRIDE", None) is not None:
        return bool(_setting("FEDERATION_OPERATIONAL_OVERRIDE"))
    if not _setting("FEDERATION_ENABLED", False):
        return False
    operational, _reason = refresh_federation_operational_state()
    return operational
