"""Tests for user views."""

from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.test import RequestFactory
from django.urls import NoReverseMatch
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from sds_gateway.users.forms import UserAdminChangeForm
from sds_gateway.users.models import User
from sds_gateway.users.tests.factories import UserFactory
from sds_gateway.users.views import UserRedirectView
from sds_gateway.users.views import UserUpdateView
from sds_gateway.users.views import user_detail_view

if TYPE_CHECKING:
    from django.core.handlers.wsgi import WSGIRequest

pytestmark = pytest.mark.django_db


class TestUserUpdateView:
    """
    TODO:
        extracting view initialization code as class-scoped fixture
        would be great if only pytest-django supported non-function-scoped
        fixture db access -- this is a work-in-progress for now:
        https://github.com/pytest-dev/pytest-django/pull/258
    """

    def dummy_get_response(self, request: HttpRequest) -> HttpResponse:
        response = HttpResponseRedirect("/")
        response.status_code = HTTPStatus.OK
        return response

    def test_get_success_url(self, user: User, rf: RequestFactory) -> None:
        view = UserUpdateView()
        request: WSGIRequest = rf.get("/fake-url/")
        request.user = user

        view.request = request
        assert view.get_success_url() == f"/users/{user.pk}/"

    def test_get_object(self, user: User, rf: RequestFactory) -> None:
        view = UserUpdateView()
        request: WSGIRequest = rf.get("/fake-url/")
        request.user = user

        view.request = request

        assert view.get_object() == user

    def test_form_valid(self, user: User, rf: RequestFactory) -> None:
        view = UserUpdateView()
        request: WSGIRequest = rf.get("/fake-url/")

        # Add the session/message middleware to the request
        SessionMiddleware(self.dummy_get_response).process_request(request)
        MessageMiddleware(self.dummy_get_response).process_request(request)
        request.user = user

        view.request = request

        # Initialize the form
        form = UserAdminChangeForm()
        form.cleaned_data = {}
        form.instance = user
        view.form_valid(form)

        messages_sent = [m.message for m in messages.get_messages(request)]
        assert messages_sent == [_("Information successfully updated")]


class TestUserRedirectView:
    def test_get_redirect_url(self, user: User, rf: RequestFactory) -> None:
        """Expects the user to be redirected to the API key generation page."""
        view = UserRedirectView()
        redirect_to: str = reverse("users:generate_api_key")
        request: WSGIRequest = rf.get("/fake-url")
        request.user = user

        view.request = request
        assert view.get_redirect_url() == redirect_to


class TestUserDetailView:
    def test_authenticated_get_works(self, user: User, rf: RequestFactory) -> None:
        """Expects the user to be able to access the view."""
        request: WSGIRequest = rf.get("/fake-url/")
        request.user = UserFactory()
        response = user_detail_view(request, pk=user.pk)

        assert response.status_code == HTTPStatus.OK

    def test_non_authenticated_redirects_user(
        self,
        user: User,
        rf: RequestFactory,
    ) -> None:
        """Expects the user to be redirected to the login page."""
        request = rf.get("/fake-url/")
        request.user = AnonymousUser()
        response = user_detail_view(request, pk=user.pk)
        try:
            login_url = reverse("auth0_login")
        except NoReverseMatch:
            login_url = reverse(settings.LOGIN_URL)

        assert isinstance(response, HttpResponseRedirect)
        assert response.status_code == HTTPStatus.FOUND
        assert response.url == f"{login_url}?next=/fake-url/"
