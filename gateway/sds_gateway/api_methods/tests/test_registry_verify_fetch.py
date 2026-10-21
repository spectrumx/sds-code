from __future__ import annotations

import socket
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.test import override_settings

from sds_gateway.api_methods.federation.registry_verify_fetch import (
    RegistryVerifyFetchError,
)
from sds_gateway.api_methods.federation.registry_verify_fetch import (
    fetch_well_known_json,
)
from sds_gateway.api_methods.federation.registry_verify_fetch import (
    validate_applicant_hostname_for_verify,
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
            "sds_gateway.api_methods.federation.registry_verify_fetch.socket.getaddrinfo",
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443)),
            ],
        ),
        pytest.raises(RegistryVerifyFetchError, match="not allowed"),
    ):
        validate_applicant_hostname_for_verify("evil.example.edu")


@override_settings(ADMIN_CONSOLE_ENV="production", SDS_SITE_FQDN="sds.crc.nd.edu")
@patch(
    "sds_gateway.api_methods.federation.registry_verify_fetch._pinned_https_get",
    return_value=(200, b'{"fqdn":"public.example.edu"}'),
)
@patch(
    "sds_gateway.api_methods.federation.registry_verify_fetch.socket.getaddrinfo",
    return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ],
)
def test_fetch_uses_pinned_https(
    mock_getaddrinfo: MagicMock,
    mock_pinned_get: MagicMock,
) -> None:
    payload = fetch_well_known_json("public.example.edu")
    assert payload["fqdn"] == "public.example.edu"
    mock_pinned_get.assert_called_once()
    assert mock_pinned_get.call_args.args[2] == ["93.184.216.34"]


@override_settings(ADMIN_CONSOLE_ENV="production", SDS_SITE_FQDN="sds.crc.nd.edu")
@patch(
    "sds_gateway.api_methods.federation.registry_verify_fetch.socket.getaddrinfo",
)
def test_fetch_dns_rebind_does_not_use_second_resolution(
    mock_getaddrinfo: MagicMock,
) -> None:
    mock_getaddrinfo.return_value = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ]

    with patch(
        "sds_gateway.api_methods.federation.registry_verify_fetch._pinned_https_get",
        return_value=(200, b'{"fqdn":"public.example.edu"}'),
    ) as mock_pinned_get:
        fetch_well_known_json("public.example.edu")

    assert mock_getaddrinfo.call_count == 1
    mock_pinned_get.assert_called_once_with(
        "https://public.example.edu/.well-known/sds-federation.json",
        "public.example.edu",
        ["93.184.216.34"],
        30,
    )


@override_settings(ADMIN_CONSOLE_ENV="production", SDS_SITE_FQDN="sds.crc.nd.edu")
@patch(
    "sds_gateway.api_methods.federation.registry_verify_fetch.socket.getaddrinfo",
    return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ],
)
def test_fetch_error_message_is_generic(mock_getaddrinfo: MagicMock) -> None:
    with (
        patch(
            "sds_gateway.api_methods.federation.registry_verify_fetch._pinned_https_get",
            side_effect=OSError("connection refused"),
        ),
        pytest.raises(RegistryVerifyFetchError, match="Could not fetch"),
    ):
        fetch_well_known_json("public.example.edu")
    assert mock_getaddrinfo.called
