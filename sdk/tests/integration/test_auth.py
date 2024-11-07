"""Integration tests with SDS for testing authentication.

Use the integration_client fixture for these tests.
"""

import pytest
from spectrumx import Client
from spectrumx.errors import AuthError


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    [
        [
            "https://sds.crc.nd.edu:443/api/v1/auth",
            "http://localhost:80/api/v1/auth",
        ]
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
