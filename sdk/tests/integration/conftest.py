"""Fixtures and utilities for integration tests."""

# better traceback formatting with rich, if available
import re
from collections.abc import Generator
from collections.abc import Sequence
from pathlib import Path
from re import Pattern

import dotenv
import pytest
from loguru import logger as log
from responses import RequestsMock
from spectrumx.client import Client
from spectrumx.gateway import API_PATH
from spectrumx.gateway import API_TARGET_VERSION
from spectrumx.gateway import Endpoints

# matches UUIDv4 strings for passthru validation
uuid_v4_regex = (
    r"[0-9a-fA-F]{{8}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]"
    r"{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{12}}"
)

dir_integration_data = Path(__file__).parent / "data"
assert dir_integration_data.exists(), (
    f"Integration test data directory '{dir_integration_data}' does not exist."
)

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


class PassthruEndpoints:
    """Wrapper to return commonly used passthru hostnames.

    Passthru hostnames are a collection of complete endpoints -- protocol + (sub+)domain
        + port + path -- that are used to bypass the `responses` package in integration
        tests. All endpoints matched by these URLs will be allowed to pass
        through to the real service behind, so that the integration can be tested.
    The method (GET, POST, etc) is not part of a passthru, so some goals share the same
        passthru URL, such as the file metadata download (GET) and file uploads (POST).
    Any requests not in the passthru list will be intercepted by `responses`, and,
        unless they are mocked, that will raise an error.

    Usage:

    Decorate a test function with the following:

    ```
    @pytest.mark.usefixtures("_without_responses")
    @pytest.mark.parametrize(
        "_without_responses",
        argvalues=[
            PassthruEndpoints.authentication(),
            # other passthru endpoints here
        ],
        # tell pytest to pass the parameters to the fixture, \
        #   instead of the test function directly:
        indirect=True,
    )
    ```

    """

    @staticmethod
    def authentication() -> list[str]:
        """Passthrough for authentication."""
        return [
            f"{hostname_and_port}{API_PATH}{API_TARGET_VERSION}{Endpoints.AUTH}"
            for hostname_and_port in passthru_hostnames
        ]

    @staticmethod
    def file_content_checks() -> list[str]:
        """Passthrough for file content checks."""
        return [
            f"{hostname_and_port}{API_PATH}{API_TARGET_VERSION}{Endpoints.FILE_CONTENTS_CHECK}"
            for hostname_and_port in passthru_hostnames
        ]

    @classmethod
    def file_uploads(cls) -> list[str]:
        """Passthrough for upload of file metadata + contents.

        Alias for file_meta_download_or_upload() to make usage more explicit.
        """
        return cls.file_meta_download_or_upload()

    @staticmethod
    def file_meta_download_or_upload() -> list[str]:
        """Passthrough for file metadata download or file uploads."""
        return [
            f"{hostname_and_port}{API_PATH}{API_TARGET_VERSION}{Endpoints.FILES}"
            for hostname_and_port in passthru_hostnames
        ]

    @staticmethod
    def file_content_download() -> list[Pattern[str]]:
        """Passthrough for file content download."""
        return [  # file content download
            re.compile(
                rf"{hostname_and_port}{API_PATH}{API_TARGET_VERSION}{Endpoints.FILES}/{uuid_v4_regex}/download"
            )
            for hostname_and_port in passthru_hostnames
        ]

    @staticmethod
    def capture_reading() -> list[Pattern[str]]:
        """Passthrough for file content download."""
        return [  # file content download
            re.compile(
                rf"{hostname_and_port}{API_PATH}{API_TARGET_VERSION}{Endpoints.CAPTURES}/{uuid_v4_regex}/"
            )
            for hostname_and_port in passthru_hostnames
        ]

    @staticmethod
    def capture_creation() -> list[str]:
        """Passthrough for capture creation."""
        return [
            f"{hostname_and_port}{API_PATH}{API_TARGET_VERSION}{Endpoints.CAPTURES}"
            for hostname_and_port in passthru_hostnames
        ]

    @staticmethod
    def capture_deletion() -> list[Pattern[str]]:
        """Passthrough for capture deletion by UUID."""
        return [
            re.compile(
                rf"{hostname_and_port}{API_PATH}{API_TARGET_VERSION}{Endpoints.CAPTURES}/{uuid_v4_regex}/"
            )
            for hostname_and_port in passthru_hostnames
        ]

    @classmethod
    def capture_listing(cls) -> list[str]:
        """Passthrough for capture listing (same as capture creation)."""
        return cls.capture_creation()

    @classmethod
    def capture_search(cls) -> list[str]:
        """Passthrough for capture search (same as capture creation)."""
        return cls.capture_creation()

    @staticmethod
    def file_deletion() -> list[Pattern[str]]:
        """Passthrough for file deletion by UUID."""
        return [
            re.compile(
                rf"{hostname_and_port}{API_PATH}{API_TARGET_VERSION}{Endpoints.FILES}/{uuid_v4_regex}/"
            )
            for hostname_and_port in passthru_hostnames
        ]

    @staticmethod
    def all_passthru() -> list[str | Pattern[str]]:
        """Returns all passthru endpoints for debugging."""
        return (
            PassthruEndpoints.authentication()
            + PassthruEndpoints.file_content_checks()
            + PassthruEndpoints.file_uploads()
            + PassthruEndpoints.file_meta_download_or_upload()
            + PassthruEndpoints.file_content_download()
            + PassthruEndpoints.capture_creation()
            + PassthruEndpoints.file_deletion()
        )


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

    ```
    @pytest.mark.integration    # optional
    @pytest.mark.usefixtures("_integration_setup_teardown")   # optional
    @pytest.mark.parametrize(
        "_without_responses",
        [
            [   # list of URLs to allow bypass (the real service is called)
                "https://sds-dev.crc.nd.edu:443{API_PATH}v1/auth",
                "http://localhost:80{API_PATH}v1/auth",
            ]
        ],
        # tell pytest to pass the parameters to this
        #   fixture, instead of the test function directly:
        indirect=True,
    )
    ```
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
    assert (
        _integration_client._config.api_key is not None  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
    ), "Client didn't load the API key."
    assert _integration_client.dry_run is False, "Dry run mode should be disabled."
    return _integration_client


@pytest.fixture
def inline_auth_integration_client() -> Client:
    """Client instance for integration testing authenticated with inline."""
    env_file = Path("tests") / "integration" / "integration.env"
    env_file_loaded = dotenv.dotenv_values(env_file, verbose=True)
    assert "SDS_SECRET_TOKEN" in env_file_loaded, (
        f"No SDS_SECRET_TOKEN found in '{env_file}'."
    )
    sds_token = env_file_loaded["SDS_SECRET_TOKEN"]
    _integration_client = Client(
        host="sds-dev.crc.nd.edu",
        env_config={
            "SDS_SECRET_TOKEN": sds_token,
            "DRY_RUN": False,
        },
        env_file=None,
        verbose=True,
    )
    assert (
        _integration_client._config.api_key is not None  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
    ), "Client didn't load the API key."
    assert _integration_client.dry_run is False, "Dry run mode should be disabled."
    return _integration_client


@pytest.fixture
def rh_sample_top_level_dir() -> Path:
    """Fixture to provide the RadioHound sample top-level directory."""
    return dir_integration_data / "captures" / "radiohound"


@pytest.fixture
def drf_sample_top_level_dir() -> Path:
    """Fixture to provide the Digital-RF sample top-level directory."""
    return dir_integration_data / "captures" / "drf" / "westford-vpol"
