"""
Tests for permission level update functionality.
"""

from django.contrib.auth import get_user_model
from django.test import Client
from django.test import TestCase
from django.urls import reverse

from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import PermissionLevel
from sds_gateway.api_methods.models import ShareGroup
from sds_gateway.api_methods.models import UserSharePermission

User = get_user_model()

# HTTP status constants
HTTP_200_OK = 200
HTTP_400_BAD_REQUEST = 400
HTTP_404_NOT_FOUND = 404


class PermissionUpdateTestCase(TestCase):
    """Test cases for permission level updates."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()

        # Create test users
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="testpass123",  # noqa: S106
            name="Dataset Owner",
        )
        self.user1 = User.objects.create_user(
            email="user1@example.com",
            password="testpass123",  # noqa: S106
            name="User One",
        )
        self.user2 = User.objects.create_user(
            email="user2@example.com",
            password="testpass123",  # noqa: S106
            name="User Two",
        )

        # Create test dataset
        self.dataset = Dataset.objects.create(
            name="Test Dataset", owner=self.owner, description="A test dataset"
        )

        # Create test group
        self.group = ShareGroup.objects.create(name="Test Group", owner=self.owner)
        self.group.members.add(self.user1, self.user2)

    def test_update_individual_user_permission(self):
        """Test updating permission level for an individual user."""
        # Create initial permission
        permission = UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.user1,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level=PermissionLevel.VIEWER,
        )

        # Login as owner
        self.client.force_login(self.owner)

        # Update permission to contributor
        response = self.client.patch(
            reverse(
                "users:share_item",
                kwargs={"item_type": "dataset", "item_uuid": self.dataset.uuid},
            ),
            data={
                "user_email": "user1@example.com",
                "permission_level": PermissionLevel.CONTRIBUTOR,
            },
        )

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert data["success"]

        # Verify permission was updated
        permission.refresh_from_db()
        assert permission.permission_level == PermissionLevel.CONTRIBUTOR

    def test_update_group_permissions(self):
        """Test updating permission levels for group members."""
        # Create permissions for group members
        permission1 = UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.user1,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level=PermissionLevel.VIEWER,
        )
        permission1.share_groups.add(self.group)

        permission2 = UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.user2,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level=PermissionLevel.VIEWER,
        )
        permission2.share_groups.add(self.group)

        # Login as owner
        self.client.force_login(self.owner)

        # Update group permissions to co-owner
        response = self.client.put(
            reverse(
                "users:share_item",
                kwargs={"item_type": "dataset", "item_uuid": self.dataset.uuid},
            ),
            data={
                "group_uuid": str(self.group.uuid),
                "permission_level": PermissionLevel.CO_OWNER,
            },
        )

        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert data["success"]

        # Verify both permissions were updated
        permission1.refresh_from_db()
        permission2.refresh_from_db()
        assert permission1.permission_level == PermissionLevel.CO_OWNER
        assert permission2.permission_level == PermissionLevel.CO_OWNER

    def test_update_permission_unauthorized(self):
        """Test that unauthorized users cannot update permissions."""
        # Create permission
        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.user1,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level=PermissionLevel.VIEWER,
        )

        # Login as user1 (not the owner)
        self.client.force_login(self.user1)

        # Try to update permission
        response = self.client.patch(
            reverse(
                "users:share_item",
                kwargs={"item_type": "dataset", "item_uuid": self.dataset.uuid},
            ),
            data={
                "user_email": "user1@example.com",
                "permission_level": PermissionLevel.CONTRIBUTOR,
            },
        )

        assert (
            response.status_code == HTTP_404_NOT_FOUND
        )  # Item not found for this user

    def test_update_permission_invalid_level(self):
        """Test that invalid permission levels are rejected."""
        # Create initial permission
        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.user1,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level=PermissionLevel.VIEWER,
        )

        # Login as owner
        self.client.force_login(self.owner)

        # Try to update with invalid permission level
        response = self.client.patch(
            reverse(
                "users:share_item",
                kwargs={"item_type": "dataset", "item_uuid": self.dataset.uuid},
            ),
            data={
                "user_email": "user1@example.com",
                "permission_level": "invalid_level",
            },
        )

        assert response.status_code == HTTP_400_BAD_REQUEST
        data = response.json()
        assert not data.get("success", True)
        assert "Invalid permission level" in data["error"]

    def test_update_permission_missing_user(self):
        """Test that updating non-existent user returns error."""
        # Login as owner
        self.client.force_login(self.owner)

        # Try to update non-existent user
        response = self.client.patch(
            reverse(
                "users:share_item",
                kwargs={"item_type": "dataset", "item_uuid": self.dataset.uuid},
            ),
            data={
                "user_email": "nonexistent@example.com",
                "permission_level": PermissionLevel.CONTRIBUTOR,
            },
        )

        assert response.status_code == HTTP_400_BAD_REQUEST
        data = response.json()
        assert not data.get("success", True)

    def test_update_group_permission_unauthorized(self):
        """Test that users cannot update group permissions they don't own."""
        # Create group owned by user1
        user1_group = ShareGroup.objects.create(name="User1 Group", owner=self.user1)
        user1_group.members.add(self.user2)

        # Create permissions
        permission = UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.user2,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level=PermissionLevel.VIEWER,
        )
        permission.share_groups.add(user1_group)

        # Login as owner (not group owner)
        self.client.force_login(self.owner)

        # Try to update group permissions
        response = self.client.put(
            reverse(
                "users:share_item",
                kwargs={"item_type": "dataset", "item_uuid": self.dataset.uuid},
            ),
            data={
                "group_uuid": str(user1_group.uuid),
                "permission_level": PermissionLevel.CONTRIBUTOR,
            },
        )

        assert response.status_code == HTTP_400_BAD_REQUEST
        data = response.json()
        assert not data.get("success", True)
