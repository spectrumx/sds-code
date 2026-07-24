"""Federation sync service operational checks for /health."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Any

import httpx
import redis.asyncio as aioredis
from opensearchpy import OpenSearch

if TYPE_CHECKING:
    from sds_federation.models import FederationConfig

_HTTP_OK = 200


@dataclass(frozen=True, slots=True)
class CheckResult:
    ok: bool
    detail: str

    def as_dict(self) -> dict[str, str | bool]:
        return {"ok": self.ok, "detail": self.detail}


def _skip_gateway_probe() -> bool:
    return os.environ.get("FEDERATION_HEALTH_SKIP_GATEWAY_PROBE", "true").lower() in (
        "1",
        "true",
        "yes",
    )


def check_config(config: FederationConfig | None) -> CheckResult:
    if config is None:
        return CheckResult(ok=False, detail="federation config not loaded")
    return CheckResult(ok=True, detail=f"site={config.site.name}")


def check_subscriber_task(task: asyncio.Task[None] | None) -> CheckResult:
    if task is None:
        return CheckResult(ok=False, detail="redis subscriber not started")
    if task.done():
        if task.cancelled():
            return CheckResult(ok=False, detail="redis subscriber cancelled")
        exc = task.exception()
        if exc is not None:
            return CheckResult(ok=False, detail=f"redis subscriber failed: {exc}")
        return CheckResult(ok=False, detail="redis subscriber stopped")
    return CheckResult(ok=True, detail="running")


async def check_redis(redis_url: str) -> CheckResult:
    client = aioredis.from_url(redis_url)
    try:
        pong = await client.ping()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(ok=False, detail=f"redis ping failed: {exc}")
    finally:
        await client.aclose()
    if not pong:
        return CheckResult(ok=False, detail="redis ping returned false")
    return CheckResult(ok=True, detail="pong")


async def check_opensearch(client: OpenSearch | None) -> CheckResult:
    if client is None:
        return CheckResult(ok=False, detail="opensearch client not configured")

    def _ping() -> bool:
        return bool(client.ping())

    try:
        alive = await asyncio.to_thread(_ping)
    except Exception as exc:  # noqa: BLE001
        return CheckResult(ok=False, detail=f"opensearch ping failed: {exc}")
    if not alive:
        return CheckResult(ok=False, detail="opensearch ping returned false")
    return CheckResult(ok=True, detail="pong")


async def check_gateway_export(
    http: httpx.AsyncClient | None,
    gateway_api_base: str,
) -> CheckResult:
    if _skip_gateway_probe():
        return CheckResult(ok=True, detail="gateway probe skipped")
    if http is None:
        return CheckResult(ok=False, detail="gateway http client not configured")
    url = f"{gateway_api_base.rstrip('/')}/federation/export/datasets/"
    try:
        resp = await http.get(url, timeout=2.0)
    except httpx.HTTPError as exc:
        return CheckResult(ok=False, detail=f"gateway export request failed: {exc}")
    if resp.status_code == _HTTP_OK:
        return CheckResult(ok=True, detail="federation export reachable")
    return CheckResult(
        ok=False,
        detail=f"gateway export returned HTTP {resp.status_code}",
    )


async def evaluate_operational(
    *,
    config: FederationConfig | None,
    http: httpx.AsyncClient | None,
    opensearch: OpenSearch | None,
    subscriber_task: asyncio.Task[None] | None,
    redis_url: str | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Return (operational, body) for the health endpoint."""
    resolved_redis = redis_url or os.environ.get(
        "REDIS_URL",
        "redis://redis:6379/0",
    )
    checks: dict[str, dict[str, str | bool]] = {
        "config": check_config(config).as_dict(),
        "redis_subscriber": check_subscriber_task(subscriber_task).as_dict(),
        "redis": (await check_redis(resolved_redis)).as_dict(),
        "opensearch": (await check_opensearch(opensearch)).as_dict(),
    }
    if not _skip_gateway_probe() and config is not None:
        checks["gateway_export"] = (
            await check_gateway_export(http, str(config.gateway_api_base))
        ).as_dict()

    failed = [name for name, result in checks.items() if not result["ok"]]
    operational = not failed
    body: dict[str, Any] = {
        "status": "ok" if operational else "unavailable",
        "checks": checks,
    }
    if failed:
        body["reason"] = f"failed checks: {', '.join(failed)}"
    return operational, body
