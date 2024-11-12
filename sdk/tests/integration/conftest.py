"""Fixtures and utilities for integration tests."""

# better traceback formatting with rich, if available
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from loguru import logger as log
from responses import RequestsMock
from spectrumx.client import Client


@pytest.fixture
def _integration_setup_teardown() -> Generator[None, None, None]:
    # setup code for integration tests
    log.debug("Setting up for integration test")

    # yield control to the test
    yield

    # teardown code for integration tests
    log.debug("Tearing down after integration test")


@pytest.fixture
def _without_responses(
    request: pytest.FixtureRequest, responses: RequestsMock
) -> Generator[None, None, None]:
    """Adds URL bypasses to the responses package.

    Used in integration tests like:

    >>> @pytest.mark.integration    # optional
        @pytest.mark.usefixtures("_integration_setup_teardown")   # optional
        @pytest.mark.parametrize(
            "_without_responses",
            [
                [   # list of URLs to allow bypass (the real service is called)
                    "https://sds.crc.nd.edu:443/api/v1/auth",
                    "http://localhost:80/api/v1/auth",
                ]
            ],
            # tell pytest to pass the parameters to this fixture, \
            #   instead of the test function directly:
            indirect=True,
        )
    """

    # setup
    responses.reset()
    bypassed_urls = request.param
    log.debug("Test allowing request bypass of the URLs:")
    for url in bypassed_urls:
        log.debug(f"  - {url}")
        responses.add_passthru(url)

    # yield control to the test
    yield

    # teardown
    log.error("Tearing down _without_responses fixture")
    responses.reset()


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


def random_bytes_generator(
    size: int, chunk: int = 1024
) -> Generator[bytes, None, None]:
    """Generates random binary data for tests."""
    for _ in range(size // chunk):
        yield os.urandom(chunk)
    yield os.urandom(size % chunk)


@pytest.fixture
@pytest.mark.slow
def temp_large_binary_file(tmp_path: Path, target_size_mb: int = 2048) -> Path:
    """Fixture to create a temporary large binary file."""
    large_binary_file = tmp_path / "large_binary_file"
    byte_generator = random_bytes_generator(1024 * 1024 * target_size_mb)
    with large_binary_file.open("wb") as f_ptr:
        for chunk in byte_generator:
            f_ptr.write(chunk)
    log.warning(
        f"Created large binary file of size: {large_binary_file.stat().st_size:,} bytes"
    )
    return large_binary_file
