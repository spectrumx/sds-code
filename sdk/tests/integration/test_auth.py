"""Integration tests with SDS for testing authentication.

Use the integration_client fixture for these tests.
"""

import pytest
from spectrumx import Client
from spectrumx.errors import AuthError

from tests.integration.conftest import PassthruEndpoints


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        PassthruEndpoints.authentication(),
    ],
    # tell pytest to pass the parameters to the fixture, \
    #   instead of the test function directly:
    indirect=True,
)
def test_authentication_200_succeeds(
    integration_client: Client,
) -> None:
    """Given a successful auth response, the client must be authenticated."""

    # auth test
    try:
        integration_client.authenticate()
        assert integration_client.is_authenticated
    except AuthError as err:
        msg = (
            "Authentication failed: make sure the api key in `integration.env` "
            "matches the server's: you need to set it manually. Error:"
            f" {err}"
        )
        pytest.fail(msg)


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        PassthruEndpoints.authentication(),
    ],
    # tell pytest to pass the parameters to the fixture, \
    #   instead of the test function directly:
    indirect=True,
)
def test_authentication_env_config_succeeds(
    inline_auth_integration_client: Client,
) -> None:
    """Tests that authentication with the inline dictionary succeeds."""

    # auth test
    inline_auth_integration_client._config.show_config()  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
    try:
        inline_auth_integration_client.authenticate()
        assert inline_auth_integration_client.is_authenticated
    except AuthError as err:
        msg = (
            "Authentication failed: make sure the api key in `integration.env` "
            "matches the server's: you need to set it manually. Error:"
            f" {err}"
        )
        pytest.fail(msg)
