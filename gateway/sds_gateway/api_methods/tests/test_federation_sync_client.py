from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import requests
from django.test import override_settings

from sds_gateway.api_methods.federation.sync_client import FederationSyncClient
from sds_gateway.api_methods.federation.sync_client import SyncUnavailableError

_SYNC_TEST_URL = "http://sync.test:8000"


@override_settings(
    FEDERATION_SYNC_INTERNAL_URL=_SYNC_TEST_URL,
    FEDERATION_SYNC_ADMIN_TOKEN="admin-token",
)
def test_verify_returns_ok_payload() -> None:
    client = FederationSyncClient.from_settings()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "ok": True,
        "well_known": {"fqdn": "peer.example.edu"},
    }
    with patch(
        "sds_gateway.api_methods.federation.sync_client.requests.request",
        return_value=mock_response,
    ) as mock_req:
        data = client.verify_domain("peer.example.edu", "abc123")
    assert data["ok"] is True
    assert mock_req.call_args.kwargs["json"]["challenge_hash"] == "abc123"


@override_settings(FEDERATION_SYNC_INTERNAL_URL="", FEDERATION_SYNC_ADMIN_TOKEN="")
def test_from_settings_requires_url() -> None:
    with pytest.raises(SyncUnavailableError):
        FederationSyncClient.from_settings()


@override_settings(
    FEDERATION_SYNC_INTERNAL_URL=_SYNC_TEST_URL,
    FEDERATION_SYNC_ADMIN_TOKEN="admin-token",
)
def test_connection_error_raises_sync_unavailable() -> None:
    client = FederationSyncClient.from_settings()
    with (
        patch(
            "sds_gateway.api_methods.federation.sync_client.requests.request",
            side_effect=requests.ConnectionError("down"),
        ),
        pytest.raises(SyncUnavailableError, match="unavailable"),
    ):
        client.verify_domain("peer.example.edu", "abc123")


@override_settings(
    FEDERATION_SYNC_INTERNAL_URL=_SYNC_TEST_URL,
    FEDERATION_SYNC_ADMIN_TOKEN="admin-token",
)
@override_settings(
    FEDERATION_SYNC_INTERNAL_URL=_SYNC_TEST_URL,
    FEDERATION_SYNC_ADMIN_TOKEN="admin-token",
)
def test_capabilities() -> None:
    client = FederationSyncClient.from_settings()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "publish_enabled": True,
        "site_fqdn": "sds.crc.nd.edu",
        "key_configured": True,
    }
    with patch(
        "sds_gateway.api_methods.federation.sync_client.requests.request",
        return_value=mock_response,
    ) as mock_req:
        data = client.capabilities()
    assert data["publish_enabled"] is True
    assert mock_req.call_args.args[0] == "GET"


@override_settings(
    FEDERATION_SYNC_INTERNAL_URL=_SYNC_TEST_URL,
    FEDERATION_SYNC_ADMIN_TOKEN="admin-token",
)
def test_publish_posts_sites() -> None:
    client = FederationSyncClient.from_settings()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "serial": 2,
        "issued_at": "2026-01-01T00:00:00Z",
        "expires_at": "2026-01-08T00:00:00Z",
        "site_names": ["crc", "peer"],
        "dry_run": False,
    }
    sites = [
        {
            "name": "peer",
            "fqdn": "peer.example.edu",
            "display_name": "Peer",
            "gateway_api_base": "https://peer.example.edu/api/v1",
            "sync_service_url": "https://peer.example.edu/sync",
            "ca_cert_file": "",
            "client_cert_fingerprints": [],
        }
    ]
    with patch(
        "sds_gateway.api_methods.federation.sync_client.requests.request",
        return_value=mock_response,
    ) as mock_req:
        data = client.publish(sites, min_serial=2, dry_run=False)
    assert data["serial"] == 2
    body = mock_req.call_args.kwargs["json"]
    assert body["min_serial"] == 2
    assert body["sites"] == sites


@override_settings(
    FEDERATION_SYNC_INTERNAL_URL=_SYNC_TEST_URL,
    FEDERATION_SYNC_ADMIN_TOKEN="admin-token",
)
def test_503_reports_admin_api_not_configured() -> None:
    client = FederationSyncClient.from_settings()
    response = MagicMock(status_code=503)
    with (
        patch(
            "sds_gateway.api_methods.federation.sync_client.requests.request",
            return_value=response,
        ),
        pytest.raises(SyncUnavailableError, match="not configured"),
    ):
        client.verify_domain("peer.example.edu", "abc123")
