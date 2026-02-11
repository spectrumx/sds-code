from __future__ import annotations

import typing

from allauth.socialaccount.models import SocialApp
from django.shortcuts import redirect
from django.urls import reverse
from loguru import logger as log

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from django.contrib.auth.models import AbstractBaseUser
    from django.contrib.auth.models import AnonymousUser
    from django.http import HttpRequest
    from django.http import HttpResponse


class SocialAccountFallbackMiddleware:
    """Middleware to gracefully handle missing SocialApp configuration.

    When a user attempts to authenticate via a social provider (e.g., Auth0)
    but the corresponding SocialApp is not configured in the database, this
    middleware catches the exception and redirects to the standard login page
    with an redirect rather than showing a 500 error.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(
        self,
        request: HttpRequest,
    ) -> HttpResponse:
        return self.get_response(request)

    def process_exception(
        self,
        request: HttpRequest,
        exception: Exception,
    ) -> HttpResponse | None:
        """Intercept SocialApp.DoesNotExist exceptions and redirect gracefully."""
        if isinstance(exception, SocialApp.DoesNotExist):
            log.warning(
                "social provider not configured, redirecting to password login",
                path=request.path,
                user=self._get_user_identifier(request.user),
            )

            # Clear any allauth session data that might interfere with password login
            session_keys_to_clear = [
                "account_login_code",
                "account_login_code_email",
                "socialaccount_state",
            ]
            for key in session_keys_to_clear:
                request.session.pop(key, None)

            return redirect(reverse("account_login"))

        return None

    def _get_user_identifier(self, user: AbstractBaseUser | AnonymousUser) -> str:
        """Get a safe user identifier for logging."""
        if user.is_authenticated:
            return getattr(user, "email", str(user.pk))
        return "anonymous"
