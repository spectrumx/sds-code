from __future__ import annotations

import socket
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
import requests
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


@patch(
    "sds_gateway.api_methods.federation.registry_verify_fetch.socket.getaddrinfo",
    return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))],
)
def test_rejects_private_resolved_ip(_mock_getaddrinfo: MagicMock) -> None:
    with pytest.raises(RegistryVerifyFetchError, match="not allowed"):
        validate_applicant_hostname_for_verify("evil.example.edu")


@override_settings(ADMIN_CONSOLE_ENV="production", SDS_SITE_FQDN="sds.crc.nd.edu")
@patch("sds_gateway.api_methods.federation.registry_verify_fetch.requests.get")
@patch(
    "sds_gateway.api_methods.federation.registry_verify_fetch.socket.getaddrinfo",
    return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ],
)
def test_fetch_disables_redirects(
    _mock_getaddrinfo: MagicMock,
    mock_get: MagicMock,
) -> None:
    response = MagicMock()
    response.content = b'{"fqdn":"public.example.edu"}'
    response.json.return_value = {"fqdn": "public.example.edu"}
    response.raise_for_status = MagicMock()
    mock_get.return_value = response

    payload = fetch_well_known_json("public.example.edu")
    assert payload["fqdn"] == "public.example.edu"
    assert mock_get.call_args.kwargs["allow_redirects"] is False


@override_settings(ADMIN_CONSOLE_ENV="production", SDS_SITE_FQDN="sds.crc.nd.edu")
@patch("sds_gateway.api_methods.federation.registry_verify_fetch.requests.get")
def test_fetch_error_message_is_generic(mock_get: MagicMock) -> None:
    mock_get.side_effect = requests.ConnectionError("connection refused")
    with (
        patch(
            "sds_gateway.api_methods.federation.registry_verify_fetch.socket.getaddrinfo",
            return_value=[
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            ],
        ),
        pytest.raises(RegistryVerifyFetchError, match="Could not fetch"),
    ):
        fetch_well_known_json("public.example.edu")
