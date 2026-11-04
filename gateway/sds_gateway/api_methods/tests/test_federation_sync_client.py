from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import requests
from django.test import override_settings

from sds_gateway.api_methods.federation.sync_client import FederationSyncClient
from sds_gateway.api_methods.federation.sync_client import SyncUnavailableError


@override_settings(
    FEDERATION_SYNC_INTERNAL_URL="http://sync.test:8000",
    FEDERATION_SYNC_ADMIN_TOKEN="admin-token",
)
def test_capabilities_success() -> None:
    client = FederationSyncClient.from_settings()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"publish_enabled": True}
    with patch(
        "sds_gateway.api_methods.federation.sync_client.requests.request",
        return_value=mock_response,
    ):
        data = client.capabilities()
    assert data["publish_enabled"] is True


@override_settings(
    FEDERATION_SYNC_INTERNAL_URL="http://sync.test:8000",
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
    FEDERATION_SYNC_INTERNAL_URL="http://sync.test:8000",
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
        client.capabilities()
