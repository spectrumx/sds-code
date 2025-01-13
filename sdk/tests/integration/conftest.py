"""Fixtures and utilities for integration tests."""

# better traceback formatting with rich, if available
from collections.abc import Generator
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from loguru import logger as log
from responses import RequestsMock
from spectrumx.client import Client

if TYPE_CHECKING:
    from re import Pattern

# add more hostnames here to bypass `responses` when running integration tests.
# these servers will receive the actual requests from integration tests:
passthru_hostnames = [
    "http://localhost:80",
    "https://sds-dev.crc.nd.edu:443",
    # "https://sds-staging.example.com:443",    # add your instance here  # noqa: ERA001
    #
    # To change the host used in these tests, see integration.env.example in this dir.
    #
    # Note: running integration tests against sds.crc.nd.edu is not recommended;
    #   but you may redirect requests to this name to a different machine by
    #   changing your local /etc/hosts first. This is useful if you're also
    #   testing your Traefik config, for example.
]


@pytest.fixture
def _integration_setup_teardown() -> Generator[None]:
    """Fixture to set up and tear down integration tests."""
    # setup code for integration tests

    # yield control to the test
    yield

    # teardown code for integration tests

    return


@pytest.fixture
def _without_responses(
    request: pytest.FixtureRequest, responses: RequestsMock
) -> Generator[None]:
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
    bypassed_urls: Sequence[str | Pattern[str]] = request.param
    log.debug("Test allowing request bypass of the URLs:")
    for url in bypassed_urls:
        log.debug(f"  - {url}")
        responses.add_passthru(url)

    # yield control to the test
    yield

    # teardown
    responses.reset()


@pytest.fixture
def integration_client() -> Client:
    """Fixture to create a Client instance for integration testing."""
    integration_config = {
        "DRY_RUN": False,  # disable dry run for integration tests
        "HTTP_TIMEOUT": 30,
        "SDS_HOST": "sds-dev.crc.nd.edu",
    }
    _integration_client = Client(
        host="sds-dev.crc.nd.edu",
        env_config=integration_config,
        env_file=Path("tests")
        / "integration"
        / "integration.env",  # contains the SDS_SECRET_TOKEN
        verbose=True,
    )
    assert _integration_client.dry_run is False, "Dry run mode should be disabled."
    return _integration_client
