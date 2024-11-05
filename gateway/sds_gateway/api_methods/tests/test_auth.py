import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory
from rest_framework.test import APITestCase
from rest_framework_api_key.models import APIKey

from sds_gateway.api_methods.authentication import APIKeyAuthentication

User = get_user_model()


class APIKeyAuthenticationTest(APITestCase):
    def setUp(self):
        # Set up any necessary data or state for the tests
        self.user = User.objects.create(
            email="test@example.com",
            password="password",  # noqa: S106
        )
        self.api_key, self.key = APIKey.objects.create_key(name="test-key")
        self.factory = APIRequestFactory()
        self.auth = APIKeyAuthentication()

    def tearDown(self):
        # Delete api_key each test method
        self.api_key.delete()

    def test_authenticate_with_valid_api_key(self):
        # Create a request with a valid API key
        request = self.factory.get(
            "/auth/",
            HTTP_AUTHORIZATION=f"Api-Key {self.key}",
        )
        user, auth = self.auth.authenticate(request)

        # Verify that the user is authenticated
        assert auth is True
        assert user is not None
        assert user.email == "test@example.com"

    def test_authenticate_with_invalid_api_key(self):
        # Create a request with an invalid API key
        request = self.factory.get(
            "/auth/",
            HTTP_AUTHORIZATION="Api-Key invalid_api_key",
        )

        # Verify that authentication fails
        with pytest.raises(AuthenticationFailed):
            self.auth.authenticate(request)

    def test_authenticate_without_api_key(self):
        # Create a request without an API key
        request = self.factory.get("/auth/")

        # Verify that authentication fails
        result = self.auth.authenticate(request)
        assert result is None
