"""Tests for user views."""

import json
import uuid
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
from django.test import Client
from django.test import RequestFactory
from django.urls import NoReverseMatch
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework import status

from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.tests.factories import DatasetFactory
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
        redirect_to: str = reverse("users:view_api_key")
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


class TestPublishDatasetView:
    """Tests for PublishDatasetView functionality."""

    @pytest.fixture
    def client(self) -> Client:
        return Client()

    @pytest.fixture
    def owner(self) -> User:
        """Create a user who owns datasets."""
        return UserFactory(is_approved=True)

    @pytest.fixture
    def other_user(self) -> User:
        """Create another user."""
        return UserFactory(is_approved=True)

    @pytest.fixture
    def draft_dataset(self, owner: User) -> Dataset:
        """Create a draft dataset owned by the owner."""
        return DatasetFactory(
            owner=owner,
            status=DatasetStatus.DRAFT,
            is_public=False,
        )

    @pytest.fixture
    def final_dataset(self, owner: User) -> Dataset:
        """Create a final (published) dataset owned by the owner."""
        return DatasetFactory(
            owner=owner,
            status=DatasetStatus.FINAL,
            is_public=False,
        )

    @pytest.fixture
    def public_dataset(self, owner: User) -> Dataset:
        """Create a public dataset owned by the owner."""
        return DatasetFactory(
            owner=owner,
            status=DatasetStatus.FINAL,
            is_public=True,
        )

    # ========== Success Cases ==========

    def test_publish_dataset_update_status_only(
        self, client: Client, owner: User, draft_dataset: Dataset
    ) -> None:
        """Test successfully updating only the status."""
        client.force_login(owner)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": draft_dataset.uuid},
        )

        data = {"status": DatasetStatus.FINAL}

        response = client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True
        assert result["message"] == "Dataset updated successfully."
        assert result["status"] == DatasetStatus.FINAL
        assert result["is_public"] is False

        # Verify database was updated
        draft_dataset.refresh_from_db()
        assert draft_dataset.status == DatasetStatus.FINAL
        assert draft_dataset.is_public is False

    def test_publish_dataset_update_is_public_only(
        self, client: Client, owner: User, draft_dataset: Dataset
    ) -> None:
        """Test that DRAFT dataset cannot be made public."""
        client.force_login(owner)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": draft_dataset.uuid},
        )

        is_public_value = True
        data = {"is_public": json.dumps(is_public_value)}

        response = client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        result = response.json()
        assert result["success"] is False
        assert "errors" in result
        assert "non_field_errors" in result["errors"]
        assert (
            "Draft datasets cannot be made public. Status must be Final."
            in result["errors"]["non_field_errors"]
        )

        # Verify database was not updated
        draft_dataset.refresh_from_db()
        assert draft_dataset.status == DatasetStatus.DRAFT
        assert draft_dataset.is_public is False

    def test_publish_dataset_update_both_fields(
        self, client: Client, owner: User, draft_dataset: Dataset
    ) -> None:
        """Test successfully updating both status and is_public."""
        client.force_login(owner)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": draft_dataset.uuid},
        )

        is_public_value = True
        data = {
            "status": DatasetStatus.FINAL,
            "is_public": json.dumps(is_public_value),
        }

        response = client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True
        assert result["message"] == "Dataset updated successfully."
        assert result["status"] == DatasetStatus.FINAL
        assert result["is_public"] is True

        # Verify database was updated
        draft_dataset.refresh_from_db()
        assert draft_dataset.status == DatasetStatus.FINAL
        assert draft_dataset.is_public is True

    def test_publish_dataset_set_is_public_false_forbidden(
        self, client: Client, owner: User, draft_dataset: Dataset
    ) -> None:
        """Test that setting is_public from True to False (private) is forbidden."""
        # First make it public
        draft_dataset.is_public = True
        draft_dataset.save()

        client.force_login(owner)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": draft_dataset.uuid},
        )

        is_public_value = False
        data = {"is_public": json.dumps(is_public_value)}

        response = client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST  # Changed from 200
        result = response.json()
        assert result["success"] is False
        assert "errors" in result
        assert (
            "Cannot change public dataset visibility back to Private."
            in result["errors"]["non_field_errors"]
        )

        # Verify database was not updated
        draft_dataset.refresh_from_db()
        assert draft_dataset.is_public is True

    # ========== Access Control Tests ==========

    def test_publish_dataset_no_access(
        self, client: Client, other_user: User, draft_dataset: Dataset
    ) -> None:
        """Test that user without access cannot publish dataset."""
        client.force_login(other_user)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": draft_dataset.uuid},
        )

        data = {"status": DatasetStatus.FINAL}

        response = client.post(url, data)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        result = response.json()
        assert result["success"] is False
        assert result["error"] == "Access denied."

        # Verify database was not updated
        draft_dataset.refresh_from_db()
        assert draft_dataset.status == DatasetStatus.DRAFT

    def test_publish_dataset_no_edit_permission(
        self,
        client: Client,
        owner: User,
        other_user: User,
        draft_dataset: Dataset,
    ) -> None:
        """Test that user without edit permission cannot publish dataset."""
        # Share dataset with other_user but only with viewer permission
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=other_user,
            item_type=ItemType.DATASET,
            item_uuid=draft_dataset.uuid,
            permission_level="viewer",
            is_enabled=True,
        )

        client.force_login(other_user)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": draft_dataset.uuid},
        )

        data = {"status": DatasetStatus.FINAL}

        response = client.post(url, data)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        result = response.json()
        assert result["success"] is False
        assert result["error"] == "You do not have permission to publish this dataset."

        # Verify database was not updated
        draft_dataset.refresh_from_db()
        assert draft_dataset.status == DatasetStatus.DRAFT

    def test_publish_dataset_with_edit_permission(
        self,
        client: Client,
        owner: User,
        other_user: User,
        draft_dataset: Dataset,
    ) -> None:
        """Test that user with co-owner permission can publish dataset."""
        # Share dataset with other_user with co-owner permission (can edit)
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=other_user,
            item_type=ItemType.DATASET,
            item_uuid=draft_dataset.uuid,
            permission_level="co-owner",
            is_enabled=True,
        )

        client.force_login(other_user)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": draft_dataset.uuid},
        )

        data = {"status": DatasetStatus.FINAL}

        response = client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True

        # Verify database was updated
        draft_dataset.refresh_from_db()
        assert draft_dataset.status == DatasetStatus.FINAL

    def test_publish_dataset_contributor_cannot_publish(
        self,
        client: Client,
        owner: User,
        other_user: User,
        draft_dataset: Dataset,
    ) -> None:
        """Test that contributor cannot publish dataset (only co-owner/owner can)."""
        # Share dataset with other_user with contributor permission
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=other_user,
            item_type=ItemType.DATASET,
            item_uuid=draft_dataset.uuid,
            permission_level="contributor",
            is_enabled=True,
        )

        client.force_login(other_user)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": draft_dataset.uuid},
        )

        data = {"status": DatasetStatus.FINAL}

        response = client.post(url, data)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        result = response.json()
        assert result["success"] is False
        assert result["error"] == "You do not have permission to publish this dataset."

        # Verify database was not updated
        draft_dataset.refresh_from_db()
        assert draft_dataset.status == DatasetStatus.DRAFT

    # ========== Validation Error Tests ==========

    def test_publish_dataset_no_fields_to_update(
        self, client: Client, owner: User, draft_dataset: Dataset
    ) -> None:
        """Test error when no fields are provided to update."""
        client.force_login(owner)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": draft_dataset.uuid},
        )

        data = {}  # No fields provided

        response = client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        result = response.json()
        assert result["success"] is False
        assert "errors" in result
        assert "non_field_errors" in result["errors"]
        assert "No fields to update." in result["errors"]["non_field_errors"]

    def test_publish_dataset_invalid_status_value(
        self, client: Client, owner: User, draft_dataset: Dataset
    ) -> None:
        """Test error when invalid status value is provided."""
        client.force_login(owner)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": draft_dataset.uuid},
        )

        data = {"status": "invalid_status"}

        response = client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        result = response.json()
        assert result["success"] is False
        assert "errors" in result
        assert "non_field_errors" in result["errors"]
        assert "Invalid status value." in result["errors"]["non_field_errors"]

    def test_publish_dataset_cannot_change_final_to_draft(
        self, client: Client, owner: User, final_dataset: Dataset
    ) -> None:
        """Test error when trying to change final status back to draft."""
        client.force_login(owner)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": final_dataset.uuid},
        )

        data = {"status": DatasetStatus.DRAFT}

        response = client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        result = response.json()
        assert result["success"] is False
        assert "errors" in result
        assert "non_field_errors" in result["errors"]
        assert (
            "Cannot change published dataset status back to Draft."
            in result["errors"]["non_field_errors"]
        )

        # Verify database was not updated
        final_dataset.refresh_from_db()
        assert final_dataset.status == DatasetStatus.FINAL

    def test_publish_dataset_cannot_change_public_to_private(
        self, client: Client, owner: User, public_dataset: Dataset
    ) -> None:
        """Test error when trying to change public dataset back to private."""
        client.force_login(owner)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": public_dataset.uuid},
        )

        is_public_value = False
        data = {"is_public": json.dumps(is_public_value)}

        response = client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        result = response.json()
        assert result["success"] is False
        assert "errors" in result
        assert "non_field_errors" in result["errors"]
        assert (
            "Cannot change public dataset visibility back to Private."
            in result["errors"]["non_field_errors"]
        )

        # Verify database was not updated
        public_dataset.refresh_from_db()
        assert public_dataset.is_public is True

    def test_publish_dataset_invalid_is_public_json(
        self, client: Client, owner: User, draft_dataset: Dataset
    ) -> None:
        """Test error when is_public contains invalid JSON."""
        client.force_login(owner)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": draft_dataset.uuid},
        )

        data = {"is_public": "not valid json"}

        response = client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        result = response.json()
        assert result["success"] is False
        assert result["error"] == "Could not determine dataset visibility."

    def test_publish_dataset_multiple_validation_errors(
        self, client: Client, owner: User, draft_dataset: Dataset
    ) -> None:
        """Test that multiple validation errors are returned."""
        client.force_login(owner)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": draft_dataset.uuid},
        )

        # Provide invalid status
        data = {"status": "invalid_status"}

        response = client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        result = response.json()
        assert result["success"] is False
        assert "errors" in result
        assert "non_field_errors" in result["errors"]
        # Should have at least the invalid status error
        assert isinstance(result["errors"]["non_field_errors"], list)
        assert len(result["errors"]["non_field_errors"]) >= 1
        assert "Invalid status value." in result["errors"]["non_field_errors"]

    def test_publish_dataset_nonexistent_dataset(
        self, client: Client, owner: User
    ) -> None:
        """Test error when dataset does not exist."""
        client.force_login(owner)
        fake_uuid = uuid.uuid4()
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": fake_uuid},
        )

        data = {"status": DatasetStatus.FINAL}

        response = client.post(url, data)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_publish_dataset_is_public_none_value(
        self, client: Client, owner: User, draft_dataset: Dataset
    ) -> None:
        """Test that is_public can be None (not provided)."""
        client.force_login(owner)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": draft_dataset.uuid},
        )

        # Only provide status, is_public should be None
        data = {"status": DatasetStatus.FINAL}

        response = client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True
        # is_public should remain unchanged (False)
        assert result["is_public"] is False

    def test_publish_dataset_make_final_public(
        self, client: Client, owner: User, final_dataset: Dataset
    ) -> None:
        """Test making a FINAL dataset public."""
        client.force_login(owner)
        url = reverse(
            "users:publish_dataset",
            kwargs={"dataset_uuid": final_dataset.uuid},
        )

        is_public_value = True
        data = {"is_public": json.dumps(is_public_value)}

        response = client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True
        assert result["status"] == DatasetStatus.FINAL
        assert result["is_public"] is True

        # Verify database was updated
        final_dataset.refresh_from_db()
        assert final_dataset.status == DatasetStatus.FINAL
        assert final_dataset.is_public is True
