from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sds_gateway.api_methods.federation.registry_application_publish_health import (
    applicant_sync_health_ok,
    publish_health_warnings_for_applications,
    sync_health_check_url,
)
from sds_gateway.api_methods.models import RegistryApplication

pytestmark = pytest.mark.django_db


def test_sync_health_check_url_appends_health() -> None:
    assert (
        sync_health_check_url("peer.example.edu", "https://peer.example.edu/sync")
        == "https://peer.example.edu/sync/health"
    )


def test_publish_health_warnings_disabled() -> None:
    app = RegistryApplication(fqdn="peer.example.edu", site_name="peer")
    assert publish_health_warnings_for_applications([app], enabled=False) == []


def test_publish_health_warnings_when_probe_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sds_gateway.api_methods.federation.registry_application_publish_health."
        "applicant_sync_health_ok",
        lambda _url, **_: False,
    )
    app = RegistryApplication(
        fqdn="peer.example.edu",
        site_name="peer",
        sync_service_url="https://peer.example.edu/sync",
    )
    warnings = publish_health_warnings_for_applications([app], enabled=True)
    assert len(warnings) == 1
    assert "peer" in warnings[0]
    assert "/sync/health" in warnings[0]


def test_applicant_sync_health_ok_accepts_status_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"status": "ok"}
    monkeypatch.setattr(
        "sds_gateway.api_methods.federation.registry_application_publish_health.requests.get",
        lambda *_a, **_k: response,
    )
    assert applicant_sync_health_ok("https://example.edu/sync/health") is True