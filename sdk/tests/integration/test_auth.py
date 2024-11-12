"""Integration tests with SDS for testing authentication.

Use the integration_client fixture for these tests.
"""

import pytest
from spectrumx import Client
from spectrumx.errors import AuthError
from spectrumx.gateway import API_TARGET_VERSION


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    [
        [
            f"https://sds.crc.nd.edu:443/api/{API_TARGET_VERSION}/auth",
            f"http://localhost:80/api/{API_TARGET_VERSION}/auth",
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
