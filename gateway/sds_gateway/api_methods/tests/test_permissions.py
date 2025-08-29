"""
Tests for the user share permission system.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model

from sds_gateway.api_methods.models import (
    Dataset, Capture, UserSharePermission, ItemType
)

User = get_user_model()


class UserSharePermissionTestCase(TestCase):
    """Test cases for the UserSharePermission model and permission checking."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="testpass123",
            name="Dataset Owner"
        )
        self.viewer = User.objects.create_user(
            email="viewer@example.com",
            password="testpass123",
            name="Dataset Viewer"
        )
        self.contributor = User.objects.create_user(
            email="contributor@example.com",
            password="testpass123",
            name="Dataset Contributor"
        )
        self.co_owner = User.objects.create_user(
            email="coowner@example.com",
            password="testpass123",
            name="Dataset Co-Owner"
        )
        
        self.dataset = Dataset.objects.create(
            name="Test Dataset",
            owner=self.owner,
            description="A test dataset"
        )
        
        self.capture = Capture.objects.create(
            name="Test Capture",
            owner=self.owner,
            dataset=self.dataset
        )

    def test_permission_levels(self):
        """Test that permission levels are correctly set and retrieved."""
        # Create permissions with different levels
        viewer_perm = UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.viewer,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="viewer"
        )
        
        contributor_perm = UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.contributor,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="contributor"
        )
        
        co_owner_perm = UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.co_owner,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="co-owner"
        )
        
        # Test permission level retrieval
        self.assertEqual(
            UserSharePermission.get_user_permission_level(
                self.viewer, self.dataset.uuid, ItemType.DATASET
            ),
            "viewer"
        )
        self.assertEqual(
            UserSharePermission.get_user_permission_level(
                self.contributor, self.dataset.uuid, ItemType.DATASET
            ),
            "contributor"
        )
        self.assertEqual(
            UserSharePermission.get_user_permission_level(
                self.co_owner, self.dataset.uuid, ItemType.DATASET
            ),
            "co-owner"
        )
        self.assertEqual(
            UserSharePermission.get_user_permission_level(
                self.owner, self.dataset.uuid, ItemType.DATASET
            ),
            "owner"
        )

    def test_permission_checking(self):
        """Test permission checking methods."""
        # Set up permissions
        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.viewer,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="viewer"
        )
        
        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.contributor,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="contributor"
        )
        
        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.co_owner,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="co-owner"
        )
        
        # Test view permissions
        self.assertTrue(
            UserSharePermission.user_can_view(self.owner, self.dataset.uuid, ItemType.DATASET)
        )
        self.assertTrue(
            UserSharePermission.user_can_view(self.viewer, self.dataset.uuid, ItemType.DATASET)
        )
        self.assertTrue(
            UserSharePermission.user_can_view(self.contributor, self.dataset.uuid, ItemType.DATASET)
        )
        self.assertTrue(
            UserSharePermission.user_can_view(self.co_owner, self.dataset.uuid, ItemType.DATASET)
        )
        
        # Test add assets permissions
        self.assertTrue(
            UserSharePermission.user_can_add_assets(self.owner, self.dataset.uuid, ItemType.DATASET)
        )
        self.assertFalse(
            UserSharePermission.user_can_add_assets(self.viewer, self.dataset.uuid, ItemType.DATASET)
        )
        self.assertTrue(
            UserSharePermission.user_can_add_assets(self.contributor, self.dataset.uuid, ItemType.DATASET)
        )
        self.assertTrue(
            UserSharePermission.user_can_add_assets(self.co_owner, self.dataset.uuid, ItemType.DATASET)
        )
        
        # Test remove assets permissions
        self.assertTrue(
            UserSharePermission.user_can_remove_assets(self.owner, self.dataset.uuid, ItemType.DATASET)
        )
        self.assertFalse(
            UserSharePermission.user_can_remove_assets(self.viewer, self.dataset.uuid, ItemType.DATASET)
        )
        self.assertFalse(
            UserSharePermission.user_can_remove_assets(self.contributor, self.dataset.uuid, ItemType.DATASET)
        )
        self.assertTrue(
            UserSharePermission.user_can_remove_assets(self.co_owner, self.dataset.uuid, ItemType.DATASET)
        )
        
        # Test edit dataset permissions
        self.assertTrue(
            UserSharePermission.user_can_edit_dataset(self.owner, self.dataset.uuid, ItemType.DATASET)
        )
        self.assertFalse(
            UserSharePermission.user_can_edit_dataset(self.viewer, self.dataset.uuid, ItemType.DATASET)
        )
        self.assertFalse(
            UserSharePermission.user_can_edit_dataset(self.contributor, self.dataset.uuid, ItemType.DATASET)
        )
        self.assertTrue(
            UserSharePermission.user_can_edit_dataset(self.co_owner, self.dataset.uuid, ItemType.DATASET)
        )

    def test_dataset_authors(self):
        """Test that dataset authors are correctly determined."""
        # Set up permissions
        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.contributor,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="contributor"
        )
        
        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.co_owner,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="co-owner"
        )
        
        # Get authors
        authors = UserSharePermission.get_dataset_authors(self.dataset.uuid)
        
        # Should have 3 authors: owner, contributor, co-owner
        self.assertEqual(len(authors), 3)
        
        # Check that all expected authors are present
        author_names = [author["name"] for author in authors]
        self.assertIn("Dataset Owner", author_names)
        self.assertIn("Dataset Contributor", author_names)
        self.assertIn("Dataset Co-Owner", author_names)
        
        # Check roles
        author_roles = {author["name"]: author["role"] for author in authors}
        self.assertEqual(author_roles["Dataset Owner"], "owner")
        self.assertEqual(author_roles["Dataset Contributor"], "contributor")
        self.assertEqual(author_roles["Dataset Co-Owner"], "co-owner")

    def test_asset_ownership_permission(self):
        """Test asset ownership permission checking."""
        from sds_gateway.api_methods.utils.permissions import check_asset_ownership_permission
        
        # Set up permissions
        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.contributor,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="contributor"
        )
        
        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.co_owner,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level="co-owner"
        )
        
        # User can always modify their own assets
        self.assertTrue(
            check_asset_ownership_permission(
                self.owner, self.owner, self.dataset.uuid, ItemType.DATASET
            )
        )
        self.assertTrue(
            check_asset_ownership_permission(
                self.contributor, self.contributor, self.dataset.uuid, ItemType.DATASET
            )
        )
        
        # Contributor cannot remove others' assets
        self.assertFalse(
            check_asset_ownership_permission(
                self.contributor, self.owner, self.dataset.uuid, ItemType.DATASET
            )
        )
        
        # Co-owner can remove others' assets
        self.assertTrue(
            check_asset_ownership_permission(
                self.co_owner, self.owner, self.dataset.uuid, ItemType.DATASET
            )
        ) 