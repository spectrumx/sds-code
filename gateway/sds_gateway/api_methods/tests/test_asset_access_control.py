"""Tests for asset access control functions with FK and M2M relationships."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import PermissionLevel
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.utils.asset_access_control import (
    get_accessible_captures_queryset,
)
from sds_gateway.api_methods.utils.asset_access_control import (
    get_accessible_files_queryset,
)
from sds_gateway.api_methods.utils.asset_access_control import (
    user_has_access_to_capture,
)
from sds_gateway.api_methods.utils.asset_access_control import user_has_access_to_file

User = get_user_model()


class AssetAccessControlTestCase(TestCase):
    """Test cases for asset access control with both FK and M2M relationships."""

    def setUp(self):
        """Set up test data."""
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="testpass123",  # noqa: S106
            name="Asset Owner",
        )
        self.viewer = User.objects.create_user(
            email="viewer@example.com",
            password="testpass123",  # noqa: S106
            name="Asset Viewer",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="testpass123",  # noqa: S106
            name="Other User",
        )

        self.dataset = Dataset.objects.create(
            name="Test Dataset", owner=self.owner, description="A test dataset"
        )

        self.capture = Capture.objects.create(
            name="Test Capture",
            owner=self.owner,
            capture_type=CaptureType.RadioHound,
            index_name="captures-rh",
            top_level_dir="test-dir",
        )

        # Share dataset with viewer
        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.viewer,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            permission_level=PermissionLevel.VIEWER,
        )

        # Share capture with viewer
        UserSharePermission.objects.create(
            owner=self.owner,
            shared_with=self.viewer,
            item_type=ItemType.CAPTURE,
            item_uuid=self.capture.uuid,
            permission_level=PermissionLevel.VIEWER,
        )

    # File access tests with FK relationships
    def test_user_has_access_to_file_via_capture_fk(self):
        """Test file access through capture FK relationship."""
        file = File.objects.create(
            name="test_file.h5",
            owner=self.owner,
            capture=self.capture,  # FK relationship
            size=1000,
        )

        # Owner should have access
        assert user_has_access_to_file(self.owner, file)
        # Viewer should have access (capture is shared)
        assert user_has_access_to_file(self.viewer, file)
        # Other user should not have access
        assert not user_has_access_to_file(self.other_user, file)

    def test_user_has_access_to_file_via_dataset_fk(self):
        """Test file access through dataset FK relationship."""
        file = File.objects.create(
            name="test_file.h5",
            owner=self.owner,
            dataset=self.dataset,  # FK relationship
            size=1000,
        )

        # Owner should have access
        assert user_has_access_to_file(self.owner, file)
        # Viewer should have access (dataset is shared)
        assert user_has_access_to_file(self.viewer, file)
        # Other user should not have access
        assert not user_has_access_to_file(self.other_user, file)

    # File access tests with M2M relationships
    def test_user_has_access_to_file_via_capture_m2m(self):
        """Test file access through capture M2M relationship."""
        file = File.objects.create(
            name="test_file.h5",
            owner=self.owner,
            size=1000,
        )
        file.captures.add(self.capture)  # M2M relationship

        # Owner should have access
        assert user_has_access_to_file(self.owner, file)
        # Viewer should have access (capture is shared)
        assert user_has_access_to_file(self.viewer, file)
        # Other user should not have access
        assert not user_has_access_to_file(self.other_user, file)

    def test_user_has_access_to_file_via_dataset_m2m(self):
        """Test file access through dataset M2M relationship."""
        file = File.objects.create(
            name="test_file.h5",
            owner=self.owner,
            size=1000,
        )
        file.datasets.add(self.dataset)  # M2M relationship

        # Owner should have access
        assert user_has_access_to_file(self.owner, file)
        # Viewer should have access (dataset is shared)
        assert user_has_access_to_file(self.viewer, file)
        # Other user should not have access
        assert not user_has_access_to_file(self.other_user, file)

    # File access tests with both FK and M2M (during migration)
    def test_user_has_access_to_file_via_both_relationships(self):
        """Test file access when both FK and M2M relationships exist."""
        file = File.objects.create(
            name="test_file.h5",
            owner=self.owner,
            capture=self.capture,  # FK
            dataset=self.dataset,  # FK
            size=1000,
        )
        file.captures.add(self.capture)  # M2M
        file.datasets.add(self.dataset)  # M2M

        # Should work with both relationships
        assert user_has_access_to_file(self.owner, file)
        assert user_has_access_to_file(self.viewer, file)
        assert not user_has_access_to_file(self.other_user, file)

    # Capture access tests
    def test_user_has_access_to_capture_via_dataset_fk(self):
        """Test capture access through dataset FK relationship."""
        capture = Capture.objects.create(
            name="Test Capture with Dataset",
            owner=self.owner,
            capture_type=CaptureType.RadioHound,
            index_name="captures-rh",
            top_level_dir="test-dir",
            dataset=self.dataset,  # FK relationship
        )

        # Owner should have access
        assert user_has_access_to_capture(self.owner, capture)
        # Viewer should have access (dataset is shared)
        assert user_has_access_to_capture(self.viewer, capture)
        # Other user should not have access
        assert not user_has_access_to_capture(self.other_user, capture)

    def test_user_has_access_to_capture_via_dataset_m2m(self):
        """Test capture access through dataset M2M relationship."""
        capture = Capture.objects.create(
            name="Test Capture with Dataset",
            owner=self.owner,
            capture_type=CaptureType.RadioHound,
            index_name="captures-rh",
            top_level_dir="test-dir",
        )
        capture.datasets.add(self.dataset)  # M2M relationship

        # Owner should have access
        assert user_has_access_to_capture(self.owner, capture)
        # Viewer should have access (dataset is shared)
        assert user_has_access_to_capture(self.viewer, capture)
        # Other user should not have access
        assert not user_has_access_to_capture(self.other_user, capture)

    # Queryset tests with FK relationships
    def test_get_accessible_files_queryset_via_capture_fk(self):
        """Test get_accessible_files_queryset with capture FK relationship."""
        file1 = File.objects.create(
            name="file1.h5",
            owner=self.owner,
            capture=self.capture,  # FK
            size=1000,
        )
        file2 = File.objects.create(
            name="file2.h5",
            owner=self.other_user,
            capture=self.capture,  # FK
            size=1000,
        )

        # Owner should see both files
        owner_files = get_accessible_files_queryset(self.owner)
        assert file1 in owner_files
        assert file2 in owner_files

        # Viewer should see both files (capture is shared)
        viewer_files = get_accessible_files_queryset(self.viewer)
        assert file1 in viewer_files
        assert file2 in viewer_files

        # Other user should not see file1 (not owned, not in accessible capture)
        # But should see file2 (owned by them, even though in shared capture)
        other_files = get_accessible_files_queryset(self.other_user)
        assert file1 not in other_files
        assert file2 in other_files  # File owner always has access

    def test_get_accessible_files_queryset_via_dataset_fk(self):
        """Test get_accessible_files_queryset with dataset FK relationship."""
        file1 = File.objects.create(
            name="file1.h5",
            owner=self.owner,
            dataset=self.dataset,  # FK
            size=1000,
        )
        file2 = File.objects.create(
            name="file2.h5",
            owner=self.other_user,
            dataset=self.dataset,  # FK
            size=1000,
        )

        # Owner should see both files
        owner_files = get_accessible_files_queryset(self.owner)
        assert file1 in owner_files
        assert file2 in owner_files

        # Viewer should see both files (dataset is shared)
        viewer_files = get_accessible_files_queryset(self.viewer)
        assert file1 in viewer_files
        assert file2 in viewer_files

        # Other user should not see file1 (not owned, not in accessible capture)
        # But should see file2 (owned by them, even though in shared capture)
        other_files = get_accessible_files_queryset(self.other_user)
        assert file1 not in other_files
        assert file2 in other_files  # File owner always has access

    # Queryset tests with M2M relationships
    def test_get_accessible_files_queryset_via_capture_m2m(self):
        """Test get_accessible_files_queryset with capture M2M relationship."""
        file1 = File.objects.create(
            name="file1.h5",
            owner=self.owner,
            size=1000,
        )
        file1.captures.add(self.capture)  # M2M

        file2 = File.objects.create(
            name="file2.h5",
            owner=self.other_user,
            size=1000,
        )
        file2.captures.add(self.capture)  # M2M

        # Owner should see both files
        owner_files = get_accessible_files_queryset(self.owner)
        assert file1 in owner_files
        assert file2 in owner_files

        # Viewer should see both files (capture is shared)
        viewer_files = get_accessible_files_queryset(self.viewer)
        assert file1 in viewer_files
        assert file2 in viewer_files

        # Other user should not see file1 (not owned, not in accessible capture)
        # But should see file2 (owned by them, even though in shared capture)
        other_files = get_accessible_files_queryset(self.other_user)
        assert file1 not in other_files
        assert file2 in other_files  # File owner always has access

    def test_get_accessible_files_queryset_via_dataset_m2m(self):
        """Test get_accessible_files_queryset with dataset M2M relationship."""
        file1 = File.objects.create(
            name="file1.h5",
            owner=self.owner,
            size=1000,
        )
        file1.datasets.add(self.dataset)  # M2M

        file2 = File.objects.create(
            name="file2.h5",
            owner=self.other_user,
            size=1000,
        )
        file2.datasets.add(self.dataset)  # M2M

        # Owner should see both files
        owner_files = get_accessible_files_queryset(self.owner)
        assert file1 in owner_files
        assert file2 in owner_files

        # Viewer should see both files (dataset is shared)
        viewer_files = get_accessible_files_queryset(self.viewer)
        assert file1 in viewer_files
        assert file2 in viewer_files

        # Other user should not see file1 (not owned, not in accessible capture)
        # But should see file2 (owned by them, even though in shared capture)
        other_files = get_accessible_files_queryset(self.other_user)
        assert file1 not in other_files
        assert file2 in other_files  # File owner always has access

    # Queryset tests with both FK and M2M
    def test_get_accessible_files_queryset_via_both_relationships(self):
        """Test get_accessible_files_queryset with both FK and M2M relationships."""
        file1 = File.objects.create(
            name="file1.h5",
            owner=self.owner,
            capture=self.capture,  # FK
            dataset=self.dataset,  # FK
            size=1000,
        )
        file1.captures.add(self.capture)  # M2M
        file1.datasets.add(self.dataset)  # M2M

        # Should work with both relationships
        owner_files = get_accessible_files_queryset(self.owner)
        assert file1 in owner_files

        viewer_files = get_accessible_files_queryset(self.viewer)
        assert file1 in viewer_files

    # Capture queryset tests
    def test_get_accessible_captures_queryset_via_dataset_fk(self):
        """Test get_accessible_captures_queryset with dataset FK relationship."""
        capture = Capture.objects.create(
            name="Test Capture",
            owner=self.owner,
            capture_type=CaptureType.RadioHound,
            index_name="captures-rh",
            top_level_dir="test-dir",
            dataset=self.dataset,  # FK
        )

        # Owner should see the capture
        owner_captures = get_accessible_captures_queryset(self.owner)
        assert capture in owner_captures

        # Viewer should see the capture (dataset is shared)
        viewer_captures = get_accessible_captures_queryset(self.viewer)
        assert capture in viewer_captures

        # Other user should not see the capture
        other_captures = get_accessible_captures_queryset(self.other_user)
        assert capture not in other_captures

    def test_get_accessible_captures_queryset_via_dataset_m2m(self):
        """Test get_accessible_captures_queryset with dataset M2M relationship."""
        capture = Capture.objects.create(
            name="Test Capture",
            owner=self.owner,
            capture_type=CaptureType.RadioHound,
            index_name="captures-rh",
            top_level_dir="test-dir",
        )
        capture.datasets.add(self.dataset)  # M2M

        # Owner should see the capture
        owner_captures = get_accessible_captures_queryset(self.owner)
        assert capture in owner_captures

        # Viewer should see the capture (dataset is shared)
        viewer_captures = get_accessible_captures_queryset(self.viewer)
        assert capture in viewer_captures

        # Other user should not see the capture
        other_captures = get_accessible_captures_queryset(self.other_user)
        assert capture not in other_captures

    # Test file ownership
    def test_file_owner_has_access(self):
        """Test that file owner always has access regardless of relationships."""
        file = File.objects.create(
            name="owned_file.h5",
            owner=self.owner,
            size=1000,
        )

        assert user_has_access_to_file(self.owner, file)
        assert file in get_accessible_files_queryset(self.owner)

    # Test nested relationships (file -> capture -> dataset)
    def test_file_access_via_capture_in_shared_dataset_fk(self):
        """Test file access through capture that belongs to shared dataset via FK."""
        capture_in_dataset = Capture.objects.create(
            name="Capture in Dataset",
            owner=self.owner,
            capture_type=CaptureType.RadioHound,
            index_name="captures-rh",
            top_level_dir="test-dir",
            dataset=self.dataset,  # FK
        )

        file = File.objects.create(
            name="file_in_capture.h5",
            owner=self.owner,
            capture=capture_in_dataset,  # FK
            size=1000,
        )

        # Viewer should have access (capture is in shared dataset)
        assert user_has_access_to_file(self.viewer, file)
        assert file in get_accessible_files_queryset(self.viewer)

    def test_file_access_via_capture_in_shared_dataset_m2m(self):
        """Test file access through capture that belongs to shared dataset via M2M."""
        capture_in_dataset = Capture.objects.create(
            name="Capture in Dataset",
            owner=self.owner,
            capture_type=CaptureType.RadioHound,
            index_name="captures-rh",
            top_level_dir="test-dir",
        )
        capture_in_dataset.datasets.add(self.dataset)  # M2M

        file = File.objects.create(
            name="file_in_capture.h5",
            owner=self.owner,
            size=1000,
        )
        file.captures.add(capture_in_dataset)  # M2M

        # Viewer should have access (capture is in shared dataset)
        assert user_has_access_to_file(self.viewer, file)
        assert file in get_accessible_files_queryset(self.viewer)
