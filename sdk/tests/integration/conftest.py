"""Fixtures and utilities for integration tests."""

# better traceback formatting with rich, if available
from pathlib import Path

import pytest
from spectrumx.client import Client


@pytest.fixture
def integration_client() -> Client:
    """Fixture to create a Client instance for integration testing."""
    integration_config = {
        "DRY_RUN": False,  # disable dry run for integration tests
        "HTTP_TIMEOUT": 30,
    }
    _integration_client = Client(
        host="sds.crc.nd.edu",
        env_config=integration_config,
        env_file=Path("tests")
        / "integration"
        / "integration.env",  # contains the SDS_SECRET_TOKEN
        verbose=True,
    )
    assert _integration_client.dry_run is False, "Dry run mode should be disabled."
    return _integration_client
