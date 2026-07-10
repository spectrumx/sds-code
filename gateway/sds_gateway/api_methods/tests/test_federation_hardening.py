"""Tests for federation operational checks and export access control."""

from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from config.settings.base import FEDERATION_EXPORT_ALLOWED_CIDRS_DEFAULT
from config.settings.base import _federation_export_allowed_cidrs_from_env
from config.settings.base import _parse_cidrs
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.test import override_settings
from django.urls import reverse
from opensearchpy import exceptions as os_exceptions
from rest_framework import status
from rest_framework.test import APITestCase

from sds_gateway.api_methods.federation.availability import (
    evaluate_federation_operational,
)
from sds_gateway.api_methods.federation.availability import (
    initialize_federation_operational_state,
)
from sds_gateway.api_methods.federation.availability import (
    is_client_ip_allowed_for_federation_export,
)
from sds_gateway.api_methods.federation.availability import (
    refresh_federation_operational_state,
)
from sds_gateway.api_methods.federation.compile_federated_data import fed_doc_exists
from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import KeySources
from sds_gateway.api_methods.tests.factories import DatasetFactory
from sds_gateway.users.models import UserAPIKey

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestFederationAvailability:
    @override_settings(FEDERATION_ENABLED=False)
    def test_disabled_when_master_switch_off(self) -> None:
        ok, reason = evaluate_federation_operational()
        assert ok is False
        assert "FEDERATION_ENABLED" in reason

    @override_settings(
        FEDERATION_ENABLED=True,
        FEDERATION_SITE_NAME="crc",
        FEDERATION_SKIP_SYNC_API_KEY_CHECK=True,
        FEDERATION_SKIP_SYNC_HEALTH_PROBE=True,
        FEDERATION_SKIP_REDIS_PROBE=True,
    )
    def test_operational_when_probes_skipped(self) -> None:
        ok, _reason = evaluate_federation_operational()
        assert ok is True

    @override_settings(
        FEDERATION_ENABLED=True,
        FEDERATION_SITE_NAME="crc",
        FEDERATION_SKIP_SYNC_HEALTH_PROBE=True,
        FEDERATION_SKIP_REDIS_PROBE=True,
    )
    def test_fails_without_sync_api_key(self) -> None:
        ok, reason = evaluate_federation_operational()
        assert ok is False
        assert "FederationSync" in reason

    @override_settings(
        FEDERATION_ENABLED=True,
        FEDERATION_SITE_NAME="crc",
        FEDERATION_SKIP_SYNC_API_KEY_CHECK=True,
        FEDERATION_SYNC_HEALTH_URL="http://sync.test/health",
        FEDERATION_SKIP_REDIS_PROBE=True,
    )
    @patch("sds_gateway.api_methods.federation.availability.urllib.request.urlopen")
    def test_health_probe_success(self, mock_urlopen: MagicMock) -> None:
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"status":"ok"}'
        response.__enter__.return_value = response
        response.__exit__.return_value = None
        mock_urlopen.return_value = response

        ok, _reason = evaluate_federation_operational()
        assert ok is True

    @override_settings(
        FEDERATION_ENABLED=True,
        FEDERATION_SITE_NAME="crc",
        FEDERATION_SKIP_SYNC_API_KEY_CHECK=True,
        FEDERATION_SYNC_HEALTH_URL="http://sync.test/health",
        FEDERATION_SKIP_REDIS_PROBE=True,
    )
    @patch("sds_gateway.api_methods.federation.availability.urllib.request.urlopen")
    def test_health_probe_fails_when_json_status_not_ok(
        self,
        mock_urlopen: MagicMock,
    ) -> None:
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"status":"degraded"}'
        response.__enter__.return_value = response
        response.__exit__.return_value = None
        mock_urlopen.return_value = response

        ok, reason = evaluate_federation_operational()
        assert ok is False
        assert "not ok" in reason

    @override_settings(
        FEDERATION_EXPORT_ALLOWED_CIDRS=["10.0.0.0/8"],
    )
    def test_client_ip_allowlist(self) -> None:
        factory = RequestFactory()
        allowed = factory.get("/", REMOTE_ADDR="10.1.2.3")
        denied = factory.get("/", REMOTE_ADDR="203.0.113.8")
        assert is_client_ip_allowed_for_federation_export(allowed) is True
        assert is_client_ip_allowed_for_federation_export(denied) is False

    @override_settings(FEDERATION_EXPORT_ALLOWED_CIDRS=[])
    def test_empty_cidr_override_falls_back_to_private_defaults(self) -> None:
        factory = RequestFactory()
        loopback = factory.get("/", REMOTE_ADDR="127.0.0.1")
        public = factory.get("/", REMOTE_ADDR="203.0.113.8")
        assert is_client_ip_allowed_for_federation_export(loopback) is True
        assert is_client_ip_allowed_for_federation_export(public) is False

    @override_settings(
        FEDERATION_ENABLED=True,
        FEDERATION_SITE_NAME="",
        FEDERATION_SKIP_SYNC_API_KEY_CHECK=True,
        FEDERATION_SKIP_SYNC_HEALTH_PROBE=True,
        FEDERATION_SKIP_REDIS_PROBE=True,
    )
    def test_fails_without_site_name(self) -> None:
        ok, reason = evaluate_federation_operational()
        assert ok is False
        assert "FEDERATION_SITE_NAME" in reason

    @override_settings(
        FEDERATION_ENABLED=True,
        FEDERATION_SITE_NAME="crc",
        FEDERATION_SKIP_SYNC_API_KEY_CHECK=True,
        FEDERATION_SKIP_SYNC_HEALTH_PROBE=True,
        FEDERATION_SKIP_REDIS_PROBE=True,
    )
    def test_refresh_sets_settings_flags(self) -> None:
        operational, reason = refresh_federation_operational_state(force=True)

        assert operational is True
        assert settings.FEDERATION_OPERATIONAL is True
        assert reason


class TestFederationExportCidrParsing:
    def test_parse_cidrs_skips_blank_tokens(self) -> None:
        networks = _parse_cidrs(["10.0.0.0/8", "", "  ", "192.168.0.0/16"])
        assert len(networks) == 2  # noqa: PLR2004

    def test_coerce_empty_env_tokens_to_defaults(self) -> None:
        with patch(
            "config.settings.base.env.list",
            return_value=["", "  "],
        ):
            networks = _federation_export_allowed_cidrs_from_env()
        assert len(networks) == len(FEDERATION_EXPORT_ALLOWED_CIDRS_DEFAULT)


class TestFederationOperationalInit:
    @override_settings(FEDERATION_ENABLED=True)
    @patch(
        "sds_gateway.api_methods.federation.availability."
        "federation_operational_db_ready",
        new=MagicMock(return_value=False),
    )
    @patch(
        "sds_gateway.api_methods.federation.availability."
        "refresh_federation_operational_state",
    )
    def test_initialize_skips_db_when_tables_missing(
        self,
        mock_refresh: MagicMock,
    ) -> None:
        initialize_federation_operational_state()
        mock_refresh.assert_not_called()
        assert settings.FEDERATION_OPERATIONAL is False
        assert settings.FEDERATION_OPERATIONAL_REASON == "database tables not ready"


@override_settings(
    FEDERATION_ENABLED=True,
    FEDERATION_SITE_NAME="crc",
    FEDERATION_OPERATIONAL_OVERRIDE=True,
    FEDERATION_EXPORT_ALLOWED_CIDRS=["0.0.0.0/0", "::/0"],
)
class FederationExportAccessControlTest(APITestCase):
    """Export API with operational + network permissions enabled for tests."""

    def setUp(self) -> None:
        self.sync_user = User.objects.create(
            email="sync@internal.local",
            is_approved=True,
        )
        _obj, self.sync_key = UserAPIKey.objects.create_key(
            name="sync",
            user=self.sync_user,
            source=KeySources.FederationSync,
        )
        owner = User.objects.create(email="owner@example.com", is_approved=True)
        self.public_dataset = DatasetFactory(
            owner=owner,
            is_public=True,
            status=DatasetStatus.FINAL,
            keywords=None,
        )
        self.list_datasets_url = reverse("api:federation-export-datasets-list")

    def _auth(self, key: str) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Api-Key: {key}"}

    def test_sync_key_allowed_from_loopback(self) -> None:
        response = self.client.get(
            self.list_datasets_url,
            REMOTE_ADDR="127.0.0.1",
            **self._auth(self.sync_key),
        )
        assert response.status_code == status.HTTP_200_OK

    @override_settings(
        FEDERATION_EXPORT_ALLOWED_CIDRS=["10.0.0.0/8"],
        FEDERATION_OPERATIONAL_OVERRIDE=True,
    )
    def test_sync_key_denied_from_public_ip(self) -> None:
        response = self.client.get(
            self.list_datasets_url,
            REMOTE_ADDR="203.0.113.1",
            **self._auth(self.sync_key),
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @override_settings(
        FEDERATION_OPERATIONAL_OVERRIDE=False,
        FEDERATION_OPERATIONAL_REASON="sync health probe failed",
        FEDERATION_EXPORT_ALLOWED_CIDRS=["0.0.0.0/0"],
    )
    def test_export_returns_503_when_not_operational(self) -> None:
        response = self.client.get(
            self.list_datasets_url,
            REMOTE_ADDR="127.0.0.1",
            **self._auth(self.sync_key),
        )
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


class TestFederationOpenSearchReads:
    @patch(
        "sds_gateway.api_methods.federation.compile_federated_data.get_opensearch_client"
    )
    def test_fed_doc_lookup_treats_cluster_errors_as_missing(
        self,
        mock_get_client: MagicMock,
    ) -> None:
        mock_get_client.return_value.get.side_effect = (
            os_exceptions.OpenSearchException(
                503,
                "connection failed",
                {},
            )
        )
        dataset = DatasetFactory(status=DatasetStatus.FINAL, is_public=True)

        assert (
            fed_doc_exists(
                asset_type=ItemType.DATASET,
                site_name="crc",
                instance=dataset,
            )
            is False
        )
