"""
Tests for the user share permission system.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import UserSharePermission

User = get_user_model()


class UserSharePermissionTestCase(TestCase):
    """Test cases for the UserSharePermission model and permission checking."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="testpass123",
            name="Dataset Owner",  # noqa: S106
        )
        self.viewer = User.objects.create_user(
            email="viewer@example.com",
            password="testpass123",
            name="Dataset Viewer",  # noqa: S106
        )
        self.contributor = User.objects.create_user(
            email="contributor@example.com",
            password="testpass123",  # noqa: S106
            name="Dataset Contributor",
        )
        self.co_owner = User.objects.create_user(
            email="coowner@example.com",
            password="testpass123",
            name="Dataset Co-Owner",  # noqa: S106
        )

        self.dataset = Dataset.objects.create(
            name="Test Dataset", owner=self.owner, description="A test dataset"
        )

        self.capture = Capture.objects.create(
            name="Test Capture", owner=self.owner, dataset=self.dataset
        )

    def test_permission_levels(self):
        """Test that permission levels are correctly set and retrieved."""
        # Create permissions with different levels
        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.viewer,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="viewer",
        )

        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.contributor,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="contributor",
        )

        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.co_owner,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="co-owner",
        )

        # Test permission level retrieval
        assert (
            UserSharePermission.get_user_permission_level(
                self.viewer, self.dataset.uuid, ItemType.DATASET
            )
            == "viewer"
        )

        assert (
            UserSharePermission.get_user_permission_level(
                self.contributor, self.dataset.uuid, ItemType.DATASET
            )
            == "contributor"
        )

        assert (
            UserSharePermission.get_user_permission_level(
                self.co_owner, self.dataset.uuid, ItemType.DATASET
            )
            == "co-owner"
        )

        assert (
            UserSharePermission.get_user_permission_level(
                self.owner, self.dataset.uuid, ItemType.DATASET
            )
            == "owner"
        )

    def test_permission_checking(self):
        """Test permission checking methods."""
        # Set up permissions
        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.viewer,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="viewer",
        )

        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.contributor,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="contributor",
        )

        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.co_owner,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="co-owner",
        )

        # Test view permissions
        assert UserSharePermission.user_can_view(
            self.owner, self.dataset.uuid, ItemType.DATASET
        )
        assert UserSharePermission.user_can_view(
            self.viewer, self.dataset.uuid, ItemType.DATASET
        )
        assert UserSharePermission.user_can_view(
            self.contributor, self.dataset.uuid, ItemType.DATASET
        )
        assert UserSharePermission.user_can_view(
            self.co_owner, self.dataset.uuid, ItemType.DATASET
        )

        # Test add assets permissions
        assert UserSharePermission.user_can_add_assets(
            self.owner, self.dataset.uuid, ItemType.DATASET
        )
        assert not UserSharePermission.user_can_add_assets(
            self.viewer, self.dataset.uuid, ItemType.DATASET
        )
        assert UserSharePermission.user_can_add_assets(
            self.contributor, self.dataset.uuid, ItemType.DATASET
        )
        assert UserSharePermission.user_can_add_assets(
            self.co_owner, self.dataset.uuid, ItemType.DATASET
        )

        # Test remove assets permissions
        assert UserSharePermission.user_can_remove_assets(
            self.owner, self.dataset.uuid, ItemType.DATASET
        )
        assert not UserSharePermission.user_can_remove_assets(
            self.viewer, self.dataset.uuid, ItemType.DATASET
        )
        assert not UserSharePermission.user_can_remove_assets(
            self.contributor, self.dataset.uuid, ItemType.DATASET
        )
        assert UserSharePermission.user_can_remove_assets(
            self.co_owner, self.dataset.uuid, ItemType.DATASET
        )

        # Test edit dataset permissions
        assert UserSharePermission.user_can_edit_dataset(
            self.owner, self.dataset.uuid, ItemType.DATASET
        )
        assert not UserSharePermission.user_can_edit_dataset(
            self.viewer, self.dataset.uuid, ItemType.DATASET
        )
        assert not UserSharePermission.user_can_edit_dataset(
            self.contributor, self.dataset.uuid, ItemType.DATASET
        )
        assert UserSharePermission.user_can_edit_dataset(
            self.co_owner, self.dataset.uuid, ItemType.DATASET
        )

    def test_dataset_authors(self):
        """Test that dataset authors are correctly determined."""
        # Set up permissions
        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.contributor,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="contributor",
        )

        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.co_owner,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="co-owner",
        )

        # Get authors
        authors = UserSharePermission.get_dataset_authors(self.dataset.uuid)

        # Should have 1 author: owner (only owner is returned by get_dataset_authors)
        assert len(authors) == 1

        # Check that owner is present
        author_names = [author["name"] for author in authors]
        assert "Dataset Owner" in author_names

        # Check role
        author_roles = {author["name"]: author["role"] for author in authors}
        assert author_roles["Dataset Owner"] == "owner"

    def test_asset_ownership_permission(self):
        """Test asset ownership permission checking using model methods."""
        # Set up permissions
        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.contributor,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="contributor",
        )

        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.co_owner,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="co-owner",
        )

        # User can always modify their own assets (owner always has remove permissions)
        assert UserSharePermission.user_can_remove_others_assets(
            self.owner, self.dataset.uuid, ItemType.DATASET
        )

        # Contributor cannot remove others' assets
        assert not UserSharePermission.user_can_remove_others_assets(
            self.contributor, self.dataset.uuid, ItemType.DATASET
        )

        # Co-owner can remove others' assets
        assert UserSharePermission.user_can_remove_others_assets(
            self.co_owner, self.dataset.uuid, ItemType.DATASET
        )
