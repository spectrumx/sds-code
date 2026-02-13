"""Tests for context processors."""

import pytest
from django.conf import settings
from django.test import RequestFactory

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
