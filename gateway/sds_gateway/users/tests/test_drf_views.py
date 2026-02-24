"""Tests for the DRF views of the users app."""

import json
import uuid

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import ShareGroup
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.users.api.views import UserViewSet
from sds_gateway.users.models import User
from sds_gateway.users.utils import update_or_create_user_group_share_permissions
from sds_gateway.users.views import _get_captures_for_template

# Test constants
TEST_PASSWORD = "testpass123"  # noqa: S105
EXPECTED_PERMISSIONS_COUNT = 2

API_VERSION = settings.API_VERSION


class TestUserViewSet:
    @pytest.fixture
    def api_rf(self) -> APIRequestFactory:
        return APIRequestFactory()

    def test_get_queryset(self, user: User, api_rf: APIRequestFactory) -> None:
        view = UserViewSet()
        request = api_rf.get("/fake-url/")
        request.user = user

        view.request = request

        assert user in view.get_queryset()

    def test_me(self, user: User, api_rf: APIRequestFactory) -> None:
        view = UserViewSet()
        request = api_rf.get("/fake-url/")
        request.user = user

        view.request = request

        response = view.me(request)  # type: ignore[call-arg, arg-type, misc]

        assert response.data == {
            "url": f"http://testserver/api/{API_VERSION}/users/{user.pk}/",
            "name": user.name,
            "email": user.email,
        }


@pytest.mark.django_db
class TestShareItemView:
    """Tests for the ShareItemView functionality."""

    @pytest.fixture
    def client(self) -> Client:
        return Client()

    @pytest.fixture
    def owner(self) -> User:
        """Create a user who owns items."""
        return User.objects.create_user(
            email="owner@example.com",
            password=TEST_PASSWORD,
            name="Owner User",
            is_approved=True,
        )

    @pytest.fixture
    def user_to_share_with(self) -> User:
        """Create a user to share items with."""
        return User.objects.create_user(
            email="share@example.com",
            password=TEST_PASSWORD,
            name="Share User",
            is_approved=True,
        )

    @pytest.fixture
    def dataset(self, owner: User) -> Dataset:
        """Create a dataset owned by the owner."""
        return Dataset.objects.create(
            uuid=uuid.uuid4(),
            name="Test Dataset",
            owner=owner,
            description="A test dataset",
        )

    @pytest.fixture(autouse=True)
    def cleanup_permissions(self, owner: User):
        """Clean up permissions after each test to prevent conflicts."""
        yield  # This runs the test
        # This runs after the test
        UserSharePermission.objects.filter(
            owner=owner,
        ).delete()

    def test_share_dataset_not_owner(
        self, client: Client, user_to_share_with: User, dataset: Dataset
    ) -> None:
        """Test sharing a dataset when user is not the owner."""
        client.force_login(user_to_share_with)
        url = reverse(
            "users:share_item",
            kwargs={"item_type": ItemType.DATASET, "item_uuid": dataset.uuid},
        )

        response = client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND, (
            f"Response: {response.content}"
        )
        assert "Dataset not found" in response.json()["error"], (
            f"Response: {response.content}"
        )

    def test_share_dataset_post_success(
        self, client: Client, owner: User, user_to_share_with: User, dataset: Dataset
    ) -> None:
        """Test successful POST request to share a dataset."""
        client.force_login(owner)
        url = reverse(
            "users:share_item",
            kwargs={"item_type": ItemType.DATASET, "item_uuid": dataset.uuid},
        )

        data = {
            "user-search": user_to_share_with.email,
            "notify_message": "Check out this dataset!",
            "notify_users": "1",
        }

        response = client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True
        assert "Added 1 user(s)" in result["message"]

        # Verify the share permission was created
        permission = UserSharePermission.objects.get(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            owner=owner,
            shared_with=user_to_share_with,
        )
        assert permission.is_enabled is True
        assert permission.message == "Check out this dataset!"

    def test_share_already_shared_user(
        self, client: Client, owner: User, user_to_share_with: User, dataset: Dataset
    ) -> None:
        """Test sharing with a user who already has access."""
        # First, share the dataset
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=user_to_share_with,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            is_enabled=True,
        )

        client.force_login(owner)
        url = reverse(
            "users:share_item",
            kwargs={"item_type": ItemType.DATASET, "item_uuid": dataset.uuid},
        )

        data = {
            "user-search": user_to_share_with.email,
            "notify_message": "Check out this dataset again!",
        }

        response = client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is False
        assert "already shared" in str(result["details"]["errors"])

    def test_share_re_enable_disabled_permission(
        self, client: Client, owner: User, user_to_share_with: User, dataset: Dataset
    ) -> None:
        """Test re-enabling a disabled share permission."""

        # Create a disabled share permission
        permission = UserSharePermission.objects.create(
            owner=owner,
            shared_with=user_to_share_with,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            is_enabled=False,
            message="Old message",
        )

        client.force_login(owner)
        url = reverse(
            "users:share_item",
            kwargs={"item_type": ItemType.DATASET, "item_uuid": dataset.uuid},
        )

        data = {
            "user-search": user_to_share_with.email,
            "notify_message": "New message",
        }

        response = client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True

        # Verify the permission was re-enabled
        permission.refresh_from_db()
        assert permission.is_enabled is True
        assert permission.message == "New message"

    def test_remove_user_from_sharing(
        self, client: Client, owner: User, user_to_share_with: User, dataset: Dataset
    ) -> None:
        """Test removing a user from sharing."""
        # First, share the dataset
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=user_to_share_with,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            is_enabled=True,
        )

        client.force_login(owner)
        url = reverse(
            "users:share_item",
            kwargs={"item_type": ItemType.DATASET, "item_uuid": dataset.uuid},
        )

        data = {
            "user-search": "",
            "remove_users": json.dumps([user_to_share_with.email]),
        }

        response = client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True
        assert "Removed 1 user(s)" in result["message"]

        # Verify the permission was disabled
        permission = UserSharePermission.objects.get(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            owner=owner,
            shared_with=user_to_share_with,
        )
        assert permission.is_enabled is False

    def test_remove_user_not_shared(
        self, client: Client, owner: User, user_to_share_with: User, dataset: Dataset
    ) -> None:
        """Test removing a user who isn't shared."""
        client.force_login(owner)
        url = reverse(
            "users:share_item",
            kwargs={"item_type": ItemType.DATASET, "item_uuid": dataset.uuid},
        )

        data = {
            "user-search": "",
            "remove_users": json.dumps([user_to_share_with.email]),
        }

        response = client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is False
        assert "not shared" in str(result["details"]["errors"])

    def test_share_with_multiple_users(
        self, client: Client, owner: User, user_to_share_with: User, dataset: Dataset
    ) -> None:
        """Test sharing with multiple users at once."""
        # Create another user
        user2 = User.objects.create_user(
            email="user2@example.com",
            password=TEST_PASSWORD,
            name="User 2",
            is_approved=True,
        )

        client.force_login(owner)
        url = reverse(
            "users:share_item",
            kwargs={"item_type": ItemType.DATASET, "item_uuid": dataset.uuid},
        )

        data = {
            "user-search": f"{user_to_share_with.email}, {user2.email}",
            "notify_message": "Check out this dataset!",
        }

        response = client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True
        assert "Added 2 user(s)" in result["message"]

        # Verify both permissions were created
        permissions = UserSharePermission.objects.filter(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            owner=owner,
        )
        assert permissions.count() == EXPECTED_PERMISSIONS_COUNT
        assert permissions.filter(shared_with=user_to_share_with).exists()
        assert permissions.filter(shared_with=user2).exists()

    def test_unified_download_dataset_success(
        self, client: Client, owner: User, dataset: Dataset
    ) -> None:
        """Test successful download request using the unified download endpoint."""
        client.force_login(owner)
        url = reverse(
            "users:download_item",
            kwargs={"item_type": ItemType.DATASET, "item_uuid": dataset.uuid},
        )

        response = client.post(url)

        assert response.status_code == status.HTTP_202_ACCEPTED
        result = response.json()
        assert result["success"] is True
        assert "download request accepted" in result["message"].lower()
        assert "task_id" in result
        assert result["item_name"] == dataset.name
        assert result["user_email"] == owner.email

    def test_unified_download_dataset_not_owner(
        self, client: Client, user_to_share_with: User, dataset: Dataset
    ) -> None:
        """Test download request when user is not the owner."""
        client.force_login(user_to_share_with)
        url = reverse(
            "users:download_item",
            kwargs={"item_type": ItemType.DATASET, "item_uuid": dataset.uuid},
        )

        response = client.post(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        result = response.json()
        assert result["success"] is False
        assert "not found or access denied" in result["message"].lower()

    def test_unified_download_dataset_invalid_type(
        self, client: Client, owner: User, dataset: Dataset
    ) -> None:
        """Test download request with invalid item type."""
        client.force_login(owner)
        url = reverse(
            "users:download_item",
            kwargs={"item_type": "invalid_type", "item_uuid": dataset.uuid},
        )

        response = client.post(url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        result = response.json()
        assert result["success"] is False
        assert "invalid item type" in result["message"].lower()

    def test_share_with_group_individual_members_already_shared(
        self, client: Client, owner: User, user_to_share_with: User, dataset: Dataset
    ) -> None:
        """
        Test sharing with a group when some members
        are already shared individually.
        """
        # Create another user for the group
        user2 = User.objects.create_user(
            email="user2@example.com",
            password=TEST_PASSWORD,
            name="User 2",
            is_approved=True,
        )

        # Create a share group

        share_group = ShareGroup.objects.create(name="Test Group", owner=owner)
        share_group.members.add(user_to_share_with, user2)

        # First, share the dataset with one of the group members individually
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=user_to_share_with,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            is_enabled=True,
            message="Individual share",
        )

        client.force_login(owner)
        url = reverse(
            "users:share_item",
            kwargs={"item_type": ItemType.DATASET, "item_uuid": dataset.uuid},
        )

        # Share with the group (should not throw an error)
        data = {
            "user-search": f"group:{share_group.uuid}",
            "notify_message": "Check out this dataset!",
        }

        response = client.post(url, data)

        # Should succeed without error
        assert response.status_code == status.HTTP_200_OK
        result = response.json()
        assert result["success"] is True

        # Verify both users now have permissions associated with the group
        permissions = UserSharePermission.objects.filter(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            owner=owner,
        )

        # Should have 2 permissions (one for each group member)
        expected_permissions = 2
        assert permissions.count() == expected_permissions

        # Check that both users have permissions with the group association
        user1_permission = permissions.filter(shared_with=user_to_share_with).first()
        user2_permission = permissions.filter(shared_with=user2).first()

        assert user1_permission is not None
        assert user2_permission is not None
        assert share_group in user1_permission.share_groups.all()
        assert share_group in user2_permission.share_groups.all()
        assert user1_permission.is_enabled is True
        assert user2_permission.is_enabled is True

        # The originally individual permission should now be associated with the group
        assert user1_permission.message == "Check out this dataset!"

    def test_capture_share_modal_displays_groups_properly(
        self, client: Client, owner: User, user_to_share_with: User, dataset: Dataset
    ) -> None:
        """
        Test that capture share modal displays groups
        properly instead of individual members.
        """
        # Create another user for the group
        user2 = User.objects.create_user(
            email="user2@example.com",
            password=TEST_PASSWORD,
            name="User 2",
            is_approved=True,
        )

        # Create a capture

        capture = Capture.objects.create(
            uuid=uuid.uuid4(),
            name="Test Capture",
            owner=owner,
            capture_type="test",
            top_level_dir="/test",
            index_name="test-index",
        )

        # Create a share group

        share_group = ShareGroup.objects.create(name="Test Group", owner=owner)
        share_group.members.add(user_to_share_with, user2)

        # Share the capture with the group

        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=share_group,
            share_user=user_to_share_with,
            item_uuid=capture.uuid,
            item_type=ItemType.CAPTURE,
            message="Group share",
        )
        update_or_create_user_group_share_permissions(
            request_user=owner,
            group=share_group,
            share_user=user2,
            item_uuid=capture.uuid,
            item_type=ItemType.CAPTURE,
            message="Group share",
        )

        client.force_login(owner)
        url = reverse("users:capture_list")

        response = client.get(url)

        # Should succeed
        assert response.status_code == status.HTTP_200_OK

        # The template should contain the group information
        # We can't easily test the JavaScript rendering,
        # but we can verify the data is prepared correctly
        # by checking that the capture has the right shared_users structure

        # Get the capture data using the same function the view uses

        captures_data = _get_captures_for_template([capture], response.wsgi_request)

        assert len(captures_data) == 1
        capture_data = captures_data[0]

        # Should have shared_users
        assert "shared_users" in capture_data
        shared_users = capture_data["shared_users"]

        # Should have exactly one group entry (not individual users)
        assert len(shared_users) == 1

        group_entry = shared_users[0]
        assert group_entry["type"] == "group"
        assert group_entry["name"] == "Test Group"
        assert group_entry["email"] == f"group:{share_group.uuid}"
        expected_members = 2
        assert group_entry["member_count"] == expected_members
        assert len(group_entry["members"]) == expected_members

        # Verify the members are correct
        member_emails = [member["email"] for member in group_entry["members"]]
        assert user_to_share_with.email in member_emails
        assert user2.email in member_emails
