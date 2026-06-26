"""Federation sync service operational checks for /health."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx
import redis.asyncio as aioredis
from opensearchpy import OpenSearch

from sds_federation.models import FederationConfig


@dataclass(frozen=True, slots=True)
class CheckResult:
    ok: bool
    detail: str

    def as_dict(self) -> dict[str, str | bool]:
        return {"ok": self.ok, "detail": self.detail}


def _skip_gateway_probe() -> bool:
    return os.environ.get("FEDERATION_HEALTH_SKIP_GATEWAY_PROBE", "").lower() in (
        "1",
        "true",
        "yes",
    )


def check_config(config: FederationConfig | None) -> CheckResult:
    if config is None:
        return CheckResult(False, "federation config not loaded")
    return CheckResult(True, f"site={config.site.name}")


def check_subscriber_task(task: asyncio.Task[None] | None) -> CheckResult:
    if task is None:
        return CheckResult(False, "redis subscriber not started")
    if task.done():
        if task.cancelled():
            return CheckResult(False, "redis subscriber cancelled")
        exc = task.exception()
        if exc is not None:
            return CheckResult(False, f"redis subscriber failed: {exc}")
        return CheckResult(False, "redis subscriber stopped")
    return CheckResult(True, "running")


async def check_redis(redis_url: str) -> CheckResult:
    client = aioredis.from_url(redis_url)
    try:
        pong = await client.ping()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(False, f"redis ping failed: {exc}")
    finally:
        await client.aclose()
    if not pong:
        return CheckResult(False, "redis ping returned false")
    return CheckResult(True, "pong")


async def check_opensearch(client: OpenSearch | None) -> CheckResult:
    if client is None:
        return CheckResult(False, "opensearch client not configured")

    def _ping() -> bool:
        return bool(client.ping())

    try:
        alive = await asyncio.to_thread(_ping)
    except Exception as exc:  # noqa: BLE001
        return CheckResult(False, f"opensearch ping failed: {exc}")
    if not alive:
        return CheckResult(False, "opensearch ping returned false")
    return CheckResult(True, "pong")


async def check_gateway_export(
    http: httpx.AsyncClient | None,
    gateway_api_base: str,
) -> CheckResult:
    if _skip_gateway_probe():
        return CheckResult(True, "gateway probe skipped")
    if http is None:
        return CheckResult(False, "gateway http client not configured")
    url = f"{gateway_api_base.rstrip('/')}/federation/export/datasets/"
    try:
        resp = await http.get(url, timeout=2.0)
    except httpx.HTTPError as exc:
        return CheckResult(False, f"gateway export request failed: {exc}")
    if resp.status_code == 200:
        return CheckResult(True, "federation export reachable")
    return CheckResult(False, f"gateway export returned HTTP {resp.status_code}")


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
    gateway_result: CheckResult
    if config is None:
        gateway_result = CheckResult(False, "federation config not loaded")
    else:
        gateway_result = await check_gateway_export(
            http,
            str(config.gateway_api_base),
        )

    checks: dict[str, dict[str, str | bool]] = {
        "config": check_config(config).as_dict(),
        "redis_subscriber": check_subscriber_task(subscriber_task).as_dict(),
        "redis": (await check_redis(resolved_redis)).as_dict(),
        "opensearch": (await check_opensearch(opensearch)).as_dict(),
        "gateway_export": gateway_result.as_dict(),
    }

    failed = [name for name, result in checks.items() if not result["ok"]]
    operational = not failed
    body: dict[str, Any] = {
        "status": "ok" if operational else "unavailable",
        "checks": checks,
    }
    if failed:
        body["reason"] = f"failed checks: {', '.join(failed)}"
    return operational, body
