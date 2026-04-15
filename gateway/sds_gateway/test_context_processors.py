"""Tests for context processors."""

import pytest
from django.conf import settings
from django.db.utils import OperationalError
from django.test import RequestFactory

from sds_gateway.context_processors import (
    _latest_admin_monitoring_status,  # pyright: ignore[reportPrivateUsage]
)
from sds_gateway.context_processors import app_settings
from sds_gateway.context_processors import branding

pytestmark = pytest.mark.django_db


class TestBrandingContextProcessor:
    """Tests for the branding context processor."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.factory = RequestFactory()

    def test_branding_returns_all_settings(self) -> None:
        """Branding context processor should return all branding settings."""
        request = self.factory.get("/")
        context = branding(request)

        assert "SDS_BRANDED_SITE_NAME" in context
        assert "SDS_FULL_INSTITUTION_NAME" in context
        assert "SDS_SHORT_INSTITUTION_NAME" in context
        assert "SDS_PROGRAMMATIC_SITE_NAME" in context
        assert "SDS_SITE_FQDN" in context

    def test_branding_values_match_settings(self) -> None:
        """Branding context values should match Django settings."""
        request = self.factory.get("/")
        context = branding(request)

        assert context["SDS_BRANDED_SITE_NAME"] == settings.SDS_BRANDED_SITE_NAME
        assert (
            context["SDS_FULL_INSTITUTION_NAME"] == settings.SDS_FULL_INSTITUTION_NAME
        )
        assert (
            context["SDS_SHORT_INSTITUTION_NAME"] == settings.SDS_SHORT_INSTITUTION_NAME
        )
        assert (
            context["SDS_PROGRAMMATIC_SITE_NAME"] == settings.SDS_PROGRAMMATIC_SITE_NAME
        )
        assert context["SDS_SITE_FQDN"] == settings.SDS_SITE_FQDN


def test_latest_admin_monitoring_status_returns_none_and_logs_for_db_error(
    monkeypatch,
    caplog,
) -> None:
    def fake_latest_snapshot_payload() -> None:
        msg = "db unavailable"
        raise OperationalError(msg)

    monkeypatch.setattr(
        "sds_gateway.monitoring.models.SystemHealthSnapshot.latest_snapshot_payload",
        fake_latest_snapshot_payload,
    )

    with caplog.at_level("WARNING"):
        result = _latest_admin_monitoring_status()

    assert result is None
    assert "failed to load admin monitoring status" in caplog.text


def test_app_settings_keeps_admin_monitoring_status_none_on_db_error(
    monkeypatch, rf
) -> None:
    def fake_latest_snapshot_payload() -> None:
        msg = "db unavailable"
        raise OperationalError(msg)

    monkeypatch.setattr(
        "sds_gateway.monitoring.models.SystemHealthSnapshot.latest_snapshot_payload",
        fake_latest_snapshot_payload,
    )

    context = app_settings(rf.get("/"))

    assert context["ADMIN_MONITORING_STATUS"] is None
