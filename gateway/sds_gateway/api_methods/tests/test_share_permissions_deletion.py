"""Tests for user share permissions deletion when items are soft deleted."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import UserSharePermission

User = get_user_model()


class SharePermissionsDeletionTestCase(TestCase):
    """Test cases for share permissions deletion when items are soft deleted."""

    # Constants for test assertions
    EXPECTED_SHARE_PERMISSIONS_BEFORE_DELETE = 2

    def setUp(self):
        """Set up test data."""
        # Create test users
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="testpass123",  # noqa: S106
            name="Owner User",
            is_approved=True,
        )

        self.shared_user1 = User.objects.create_user(
            email="shared1@example.com",
            password="testpass123",  # noqa: S106
            name="Shared User 1",
            is_approved=True,
        )

        self.shared_user2 = User.objects.create_user(
            email="shared2@example.com",
            password="testpass123",  # noqa: S106
            name="Shared User 2",
            is_approved=True,
        )

    def test_capture_soft_delete_deletes_share_permissions(self):
        """Test that soft deleting a capture deletes all related share permissions."""
        # Create a capture
        capture = Capture.objects.create(
            owner=self.owner,
            capture_type=CaptureType.DigitalRF,
            channel="test_channel",
            top_level_dir="/test/dir",
            index_name="test_index",
        )

        # Create share permissions for multiple users
        permission1 = UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.shared_user1,
            item_type=ItemType.CAPTURE,
            item_uuid=capture.uuid,
            is_enabled=True,
            message="Test share 1",
        )

        permission2 = UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.shared_user2,
            item_type=ItemType.CAPTURE,
            item_uuid=capture.uuid,
            is_enabled=True,
            message="Test share 2",
        )

        # Verify permissions exist and are not deleted
        assert UserSharePermission.objects.filter(
            item_uuid=capture.uuid,
            item_type=ItemType.CAPTURE,
            is_deleted=False,
        ).exists(), "Share permissions should exist before soft delete"

        assert (
            UserSharePermission.objects.filter(
                item_uuid=capture.uuid,
                item_type=ItemType.CAPTURE,
                is_deleted=False,
            ).count()
            == self.EXPECTED_SHARE_PERMISSIONS_BEFORE_DELETE
        ), "Expected 2 share permissions before soft delete"

        # Soft delete the capture
        capture.soft_delete()

        # Verify the capture is soft deleted
        capture.refresh_from_db()
        assert capture.is_deleted is True, "Capture should be soft deleted"
        assert capture.deleted_at is not None, (
            "Capture should have deleted_at timestamp"
        )

        # Verify all share permissions are soft deleted
        permission1.refresh_from_db()
        permission2.refresh_from_db()

        assert permission1.is_deleted is True, "Permission1 should be soft deleted"
        assert permission2.is_deleted is True, "Permission2 should be soft deleted"
        assert permission1.deleted_at is not None, (
            "Permission1 should have deleted_at timestamp"
        )
        assert permission2.deleted_at is not None, (
            "Permission2 should have deleted_at timestamp"
        )

        # Verify no active share permissions exist for this capture
        assert not UserSharePermission.objects.filter(
            item_uuid=capture.uuid,
            item_type=ItemType.CAPTURE,
            is_deleted=False,
        ).exists(), "No active share permissions should exist after soft delete"

    def test_dataset_soft_delete_deletes_share_permissions(self):
        """Test that soft deleting a dataset deletes all related share permissions."""
        # Create a dataset
        dataset = Dataset.objects.create(
            owner=self.owner,
            name="Test Dataset",
            description="Test dataset for share permissions",
            authors=["Test Author"],
        )

        # Create share permissions for multiple users
        permission1 = UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.shared_user1,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            is_enabled=True,
            message="Test dataset share 1",
        )

        permission2 = UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.shared_user2,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            is_enabled=True,
            message="Test dataset share 2",
        )

        # Verify permissions exist and are not deleted
        assert UserSharePermission.objects.filter(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            is_deleted=False,
        ).exists(), "Dataset share permissions should exist before soft delete"

        assert (
            UserSharePermission.objects.filter(
                item_uuid=dataset.uuid,
                item_type=ItemType.DATASET,
                is_deleted=False,
            ).count()
            == self.EXPECTED_SHARE_PERMISSIONS_BEFORE_DELETE
        ), "Expected 2 dataset share permissions before soft delete"

        # Soft delete the dataset
        dataset.soft_delete()

        # Verify the dataset is soft deleted
        dataset.refresh_from_db()
        assert dataset.is_deleted is True, "Dataset should be soft deleted"
        assert dataset.deleted_at is not None, (
            "Dataset should have deleted_at timestamp"
        )

        # Verify all share permissions are soft deleted
        permission1.refresh_from_db()
        permission2.refresh_from_db()

        assert permission1.is_deleted is True, (
            "Dataset permission1 should be soft deleted"
        )
        assert permission2.is_deleted is True, (
            "Dataset permission2 should be soft deleted"
        )
        assert permission1.deleted_at is not None, (
            "Dataset permission1 should have deleted_at timestamp"
        )
        assert permission2.deleted_at is not None, (
            "Dataset permission2 should have deleted_at timestamp"
        )

        # Verify no active share permissions exist for this dataset
        assert not UserSharePermission.objects.filter(
            item_uuid=dataset.uuid,
            item_type=ItemType.DATASET,
            is_deleted=False,
        ).exists(), "No active dataset share permissions should exist after soft delete"

    def test_signal_only_triggers_on_soft_delete(self):
        """Test that the signal only triggers when is_deleted becomes True."""
        # Create a capture
        capture = Capture.objects.create(
            owner=self.owner,
            capture_type=CaptureType.DigitalRF,
            channel="test_channel",
            top_level_dir="/test/dir",
            index_name="test_index",
        )

        # Create a share permission
        permission = UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.shared_user1,
            item_type=ItemType.CAPTURE,
            item_uuid=capture.uuid,
            is_enabled=True,
        )

        # Verify permission exists
        assert UserSharePermission.objects.filter(
            item_uuid=capture.uuid,
            item_type=ItemType.CAPTURE,
            is_deleted=False,
        ).exists(), "Share permission should exist before update"

        # Update the capture without soft deleting (e.g., change the name)
        capture.name = "Updated Name"
        capture.save()

        # Verify the share permission is NOT affected
        permission.refresh_from_db()
        assert permission.is_deleted is False, (
            "Share permission should not be affected by name update"
        )

        # Verify the permission still exists
        assert UserSharePermission.objects.filter(
            item_uuid=capture.uuid,
            item_type=ItemType.CAPTURE,
            is_deleted=False,
        ).exists(), "Share permission should still exist after name update"
