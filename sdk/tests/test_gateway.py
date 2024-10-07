"""Tests for the gateway module."""

from spectrumx.gateway import Endpoints
from spectrumx.gateway import GatewayClient


def test_endpoints() -> None:
    """All endpoints must start with a slash."""
    assert all(
        endpoint.startswith("/") for endpoint in Endpoints.__members__.values()
    ), "All endpoints must start with a slash."


def test_base_url() -> None:
    """The base URL must be properly formatted."""
    gateway = GatewayClient(
        host="fake-host-for-tests.crc.nd.edu",
        api_key="123",
        port=666,
        protocol="sds",
    )
    assert gateway.base_url == "sds://fake-host-for-tests.crc.nd.edu:666"
