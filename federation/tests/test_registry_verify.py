"""Tests ported from gateway registry verify fetch (SSRF boundary)."""

from __future__ import annotations

import socket
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from sds_federation.models import FederationConfig
from sds_federation.models import SiteInfo
from sds_federation.services.registry_verify import RegistryVerifyFetchError
from sds_federation.services.registry_verify import fetch_well_known_json
from sds_federation.services.registry_verify import validate_applicant_hostname_for_verify


def _mothership_config() -> FederationConfig:
    return FederationConfig(
        site=SiteInfo(name="crc", fqdn="sds.crc.nd.edu", display_name="CRC"),
        gateway_api_base="https://sds.crc.nd.edu/api/v1",
        sync_service_url="https://sds.crc.nd.edu/sync",
        peers=[],
    )


def test_rejects_private_literal_ip() -> None:
    with pytest.raises(RegistryVerifyFetchError, match="not allowed"):
        validate_applicant_hostname_for_verify("10.0.0.1")


def test_rejects_loopback_literal_ip() -> None:
    with pytest.raises(RegistryVerifyFetchError, match="not allowed"):
        validate_applicant_hostname_for_verify("127.0.0.1")


def test_rejects_private_resolved_ip() -> None:
    with (
        patch(
            "sds_federation.services.registry_verify.socket.getaddrinfo",
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443)),
            ],
        ),
        pytest.raises(RegistryVerifyFetchError, match="not allowed"),
    ):
        validate_applicant_hostname_for_verify("evil.example.edu")


@patch(
    "sds_federation.services.registry_verify._pinned_https_get",
    return_value=b'{"fqdn":"public.example.edu"}',
)
@patch(
    "sds_federation.services.registry_verify.socket.getaddrinfo",
    return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ],
)
def test_fetch_uses_pinned_https(
    mock_getaddrinfo: MagicMock,
    mock_pinned_get: MagicMock,
) -> None:
    import asyncio

    config = _mothership_config()
    payload = asyncio.run(fetch_well_known_json("public.example.edu", config))
    assert payload["fqdn"] == "public.example.edu"
    mock_pinned_get.assert_called_once()
    assert mock_pinned_get.call_args.args[2] == ["93.184.216.34"]


@patch(
    "sds_federation.services.registry_verify.socket.getaddrinfo",
)
def test_fetch_dns_rebind_does_not_use_second_resolution(
    mock_getaddrinfo: MagicMock,
) -> None:
    import asyncio

    mock_getaddrinfo.return_value = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ]
    config = _mothership_config()

    with patch(
        "sds_federation.services.registry_verify._pinned_https_get",
        return_value=b'{"fqdn":"public.example.edu"}',
    ) as mock_pinned_get:
        asyncio.run(fetch_well_known_json("public.example.edu", config))

    assert mock_getaddrinfo.call_count == 1
    mock_pinned_get.assert_called_once_with(
        "https://public.example.edu/.well-known/sds-federation.json",
        "public.example.edu",
        ["93.184.216.34"],
        30,
    )


@patch(
    "sds_federation.services.registry_verify.socket.getaddrinfo",
    return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ],
)
def test_fetch_error_message_is_generic(mock_getaddrinfo: MagicMock) -> None:
    import asyncio

    config = _mothership_config()
    with (
        patch(
            "sds_federation.services.registry_verify._pinned_https_get",
            side_effect=OSError("connection refused"),
        ),
        pytest.raises(RegistryVerifyFetchError, match="Could not fetch"),
    ):
        asyncio.run(fetch_well_known_json("public.example.edu", config))
    assert mock_getaddrinfo.called
