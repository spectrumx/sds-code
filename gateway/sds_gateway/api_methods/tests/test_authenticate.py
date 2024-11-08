"""Tests cases for the API key authentication method."""

from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory
from rest_framework.test import APITestCase

from sds_gateway.api_methods.authentication import APIKeyAuthentication
from sds_gateway.users.models import UserAPIKey

User = get_user_model()


class APIKeyAuthenticationTest(APITestCase):
    def setUp(self) -> None:
        """Set up any necessary data or state for the tests."""
        self.user = User.objects.create(
            email="test@example.com",
            password="password",  # noqa: S106
        )
        self.api_key, self.key = UserAPIKey.objects.create_key(
            name="test-key",
            user=self.user,
        )
        self.factory = APIRequestFactory()
        self.auth = APIKeyAuthentication()

    def test_auth_valid_key(self) -> None:
        """Tests a request with a valid API key."""
        request = self.factory.get(
            "/auth/",
            HTTP_AUTHORIZATION=f"Api-Key: {self.key}",
        )
        user, auth = self.auth.authenticate(request)

        # Verify that the user is authenticated
        assert auth is True
        assert user is not None
        assert user.email == "test@example.com"

    def test_auth_no_key(self) -> None:
        """Makes sure that a request without an API key raises."""
        request = self.factory.get("/auth/")
        with self.assertRaises(AuthenticationFailed):  # noqa: PT027
            self.auth.authenticate(request)

    def test_auth_invalid_key(self) -> None:
        """Makes sure that a request with an invalid API key raises."""
        request = self.factory.get(
            "/auth/",
            HTTP_AUTHORIZATION="Api-Key: 123123123",
        )
        with self.assertRaises(AuthenticationFailed):  # noqa: PT027
            self.auth.authenticate(request)
