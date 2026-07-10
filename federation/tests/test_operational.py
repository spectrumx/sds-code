"""Unit tests for federation sync operational health checks."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import httpx
import pytest
from sds_federation.models import FederationConfig
from sds_federation.models import SiteInfo
from sds_federation.services.operational import CheckResult
from sds_federation.services.operational import check_config
from sds_federation.services.operational import check_gateway_export
from sds_federation.services.operational import check_subscriber_task
from sds_federation.services.operational import evaluate_operational


def _sample_config() -> FederationConfig:
    return FederationConfig(
        site=SiteInfo(name="testsite", fqdn="test.example", display_name="Test"),
        gateway_api_base="http://gateway:8000/api/v1",
        sync_service_url="http://test.example/sync",
    )


def test_check_config_requires_loaded_config() -> None:
    assert check_config(None).ok is False
    good = check_config(_sample_config())
    assert good.ok is True
    assert "testsite" in good.detail


@pytest.mark.asyncio
async def test_check_subscriber_task_running() -> None:
    async def _noop() -> None:
        await asyncio.sleep(3600)

    task = asyncio.create_task(_noop())
    try:
        assert check_subscriber_task(task).ok is True
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_check_subscriber_task_missing() -> None:
    assert check_subscriber_task(None).ok is False


@pytest.mark.asyncio
async def test_check_gateway_export_success() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=[]),
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with patch(
            "sds_federation.services.operational._skip_gateway_probe",
            return_value=False,
        ):
            result = await check_gateway_export(
                client,
                "http://gateway:8000/api/v1",
            )
    assert result.ok is True


@pytest.mark.asyncio
async def test_check_gateway_export_non_200() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(503, json={"detail": "unavailable"}),
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with patch(
            "sds_federation.services.operational._skip_gateway_probe",
            return_value=False,
        ):
            result = await check_gateway_export(
                client,
                "http://gateway:8000/api/v1",
            )
    assert result.ok is False
    assert "503" in result.detail


@pytest.mark.asyncio
async def test_evaluate_operational_all_pass() -> None:
    config = _sample_config()

    async def _noop() -> None:
        await asyncio.sleep(3600)

    sub_task = asyncio.create_task(_noop())
    mock_os = MagicMock()
    mock_os.ping.return_value = True

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=[]),
    )
    redis_ok = CheckResult(ok=True, detail="pong")
    try:
        async with httpx.AsyncClient(transport=transport) as http:
            with patch(
                "sds_federation.services.operational.check_redis",
                new_callable=AsyncMock,
                return_value=redis_ok,
            ):
                operational, body = await evaluate_operational(
                    config=config,
                    http=http,
                    opensearch=mock_os,
                    subscriber_task=sub_task,
                )
    finally:
        sub_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await sub_task

    assert operational is True
    assert body["status"] == "ok"
    assert body["checks"]["config"]["ok"] is True


@pytest.mark.asyncio
async def test_evaluate_operational_fails_when_subscriber_stopped() -> None:
    config = _sample_config()
    mock_os = MagicMock()
    mock_os.ping.return_value = True

    done_task = asyncio.create_task(asyncio.sleep(0))
    await done_task

    redis_ok = CheckResult(ok=True, detail="pong")
    gateway_ok = CheckResult(ok=True, detail="ok")
    with (
        patch(
            "sds_federation.services.operational.check_redis",
            new_callable=AsyncMock,
            return_value=redis_ok,
        ),
        patch(
            "sds_federation.services.operational.check_gateway_export",
            new_callable=AsyncMock,
            return_value=gateway_ok,
        ),
    ):
        operational, body = await evaluate_operational(
            config=config,
            http=MagicMock(),
            opensearch=mock_os,
            subscriber_task=done_task,
        )

    assert operational is False
    assert body["status"] == "unavailable"
    assert body["checks"]["redis_subscriber"]["ok"] is False
