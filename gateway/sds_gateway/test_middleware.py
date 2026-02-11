"""Tests for custom middleware."""

from http import HTTPStatus
from unittest.mock import Mock

import pytest
from allauth.socialaccount.models import SocialApp
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages import get_messages
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from sds_gateway.middleware import SocialAccountFallbackMiddleware

pytestmark = pytest.mark.django_db


class TestSocialAccountFallbackMiddleware:
    """Tests for SocialAccountFallbackMiddleware."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.factory = RequestFactory()
        self.get_response = Mock(return_value=HttpResponse())
        self.middleware = SocialAccountFallbackMiddleware(self.get_response)

    def _add_session_to_request(self, request: HttpRequest) -> HttpRequest:
        """Add session support to request for messages framework."""
        middleware = SessionMiddleware(self.get_response)
        middleware.process_request(request)
        request.session.save()
        return request

    def test_middleware_passes_through_normal_requests(self) -> None:
        """Middleware should not interfere with normal requests."""
        request = self.factory.get("/")
        response = self.middleware(request)

        assert response.status_code == HTTPStatus.OK
        self.get_response.assert_called_once_with(request)

    def test_middleware_catches_social_app_does_not_exist(self) -> None:
        """Middleware should catch SocialApp.DoesNotExist and redirect."""
        request = self.factory.get("/accounts/auth0/login/")
        request = self._add_session_to_request(request)
        request.user = AnonymousUser()

        exception = SocialApp.DoesNotExist()
        response = self.middleware.process_exception(request, exception)

        assert response is not None
        assert response.status_code == HTTPStatus.FOUND
        assert response["Location"] == reverse("account_login")

        messages_list = list(get_messages(request))
        assert len(messages_list) == 1
        assert "Third-party authentication is currently unavailable" in str(
            messages_list[0]
        )

    def test_middleware_ignores_other_exceptions(self) -> None:
        """Middleware should not handle exceptions other than SocialApp.DoesNotExist."""
        request = self.factory.get("/")

        exception = ValueError("some other error")
        response = self.middleware.process_exception(request, exception)

        assert response is None

    def test_middleware_logs_warning_on_social_app_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Middleware should log a warning when catching SocialApp.DoesNotExist."""
        request = self.factory.get("/accounts/auth0/login/")
        request = self._add_session_to_request(request)
        request.user = AnonymousUser()

        exception = SocialApp.DoesNotExist()
        self.middleware.process_exception(request, exception)

        assert any(
            "social provider not configured" in record.message
            for record in caplog.records
        )

    def test_get_user_identifier_with_authenticated_user(self, user) -> None:
        """Should return email for authenticated users."""
        identifier = self.middleware._get_user_identifier(user)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        assert identifier == user.email

    def test_get_user_identifier_with_anonymous_user(self) -> None:
        """Should return 'anonymous' for unauthenticated users."""
        user = AnonymousUser()
        identifier = self.middleware._get_user_identifier(user)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        assert identifier == "anonymous"
