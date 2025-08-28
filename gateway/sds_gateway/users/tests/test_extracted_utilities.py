"""
Test for the extracted utility functions.

These functions were originally methods in the FilesView class but have been
extracted to improve testability and reusability.
"""

from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.users.files_utils import add_capture_files
from sds_gateway.users.files_utils import add_root_items
from sds_gateway.users.files_utils import add_shared_items
from sds_gateway.users.files_utils import format_modified
from sds_gateway.users.files_utils import make_dir_item
from sds_gateway.users.files_utils import make_file_item
from sds_gateway.users.models import User


class FormatModifiedTestCase(TestCase):
    """Test the extracted format_modified function."""

    def test_format_modified_with_datetime(self):
        """Test formatting of datetime objects."""
        dt = timezone.now()
        result = format_modified(dt)
        assert isinstance(result, str)
        assert str(dt.year) in result
        assert str(dt.month).zfill(2) in result
        assert str(dt.day).zfill(2) in result

    def test_format_modified_with_none(self):
        """Test formatting of None values."""
        result = format_modified(None)
        assert result == "N/A"


class MakeDirItemTestCase(TestCase):
    """Test the extracted make_dir_item function."""

    def test_make_dir_item(self):
        """Test directory item creation."""
        item = make_dir_item(
            name="Test Directory",
            path="/test/path",
            uuid="123",
            is_capture=True,
            is_shared=False,
            is_owner=True,
            capture_uuid="456",
            modified_at_display="2024-01-01 12:00",
            shared_by="",
        )

        assert item["type"] == "directory"
        assert item["name"] == "Test Directory"
        assert item["path"] == "/test/path"
        assert item["uuid"] == "123"
        assert item["is_capture"]
        assert not item["is_shared"]
        assert item["is_owner"]
        assert item["capture_uuid"] == "456"
        assert item["modified_at"] == "2024-01-01 12:00"
        assert item["shared_by"] == ""

    def test_make_dir_item_with_defaults(self):
        """Test directory item creation with minimal parameters."""
        item = make_dir_item(name="Minimal Dir", path="/minimal")

        assert item["type"] == "directory"
        assert item["name"] == "Minimal Dir"
        assert item["path"] == "/minimal"
        assert item["uuid"] == ""
        assert not item["is_capture"]
        assert not item["is_shared"]
        assert not item["is_owner"]
        assert item["capture_uuid"] == ""
        assert item["modified_at"] == "N/A"
        assert item["shared_by"] == ""


class MakeFileItemTestCase(TestCase):
    """Test the extracted make_file_item function."""

    def test_make_file_item(self):
        """Test file item creation."""
        mock_file = Mock()
        mock_file.name = "test.txt"
        mock_file.uuid = "789"
        mock_file.description = "Test file"
        mock_file.updated_at = None

        item = make_file_item(
            file_obj=mock_file, capture_uuid="456", is_shared=False, shared_by=""
        )

        assert item["type"] == "file"
        assert item["name"] == "test.txt"
        assert item["uuid"] == "789"
        assert item["is_capture"] is False
        assert item["is_shared"] is False
        assert item["capture_uuid"] == "456"
        assert item["description"] == "Test file"
        assert item["modified_at"] == "N/A"
        assert item["shared_by"] == ""

    def test_make_file_item_with_updated_at(self):
        """Test file item creation with updated_at timestamp."""
        mock_file = Mock()
        mock_file.name = "test.txt"
        mock_file.uuid = "789"
        mock_file.description = "Test file"
        mock_file.updated_at = timezone.now()

        item = make_file_item(
            file_obj=mock_file,
            capture_uuid="",
            is_shared=True,
            shared_by="user@example.com",
        )

        assert item["type"] == "file"
        assert item["name"] == "test.txt"
        assert item["uuid"] == "789"
        assert not item["is_capture"]
        assert item["is_shared"]
        assert item["capture_uuid"] == ""
        assert item["description"] == "Test file"
        assert item["modified_at"] != "N/A"  # Should have formatted timestamp
        assert item["shared_by"] == "user@example.com"

    def test_make_file_item_with_missing_attributes(self):
        """Test file item creation with missing file attributes."""
        mock_file = Mock()
        mock_file.name = "test.txt"
        mock_file.uuid = "789"
        # Missing description and updated_at attributes

        item = make_file_item(
            file_obj=mock_file, capture_uuid="", is_shared=False, shared_by=""
        )

        assert item["type"] == "file"
        assert item["name"] == "test.txt"
        assert item["uuid"] == "789"
        assert item["description"] == ""  # Should default to empty string
        assert item["modified_at"] == "N/A"  # Should default to N/A


class AddRootItemsTestCase(TestCase):
    """Test the extracted add_root_items function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",  # noqa: S106
        )
        self.capture = Capture.objects.create(
            owner=self.user,
            name="Test Capture",
            uuid="123e4567-e89b-12d3-a456-426614174000",
        )
        self.file = File.objects.create(
            owner=self.user,
            name="test.txt",
            uuid="456e7890-e89b-12d3-a456-426614174000",
            directory="/test",
            is_deleted=False,
        )

    def test_add_root_items_with_captures(self):
        """Test adding root items with user captures."""
        items = []
        add_root_items(self.user, items)

        # Should have one directory item for the capture
        assert len(items) == 1
        assert items[0]["type"] == "directory"
        assert items[0]["name"] == "Test Capture"
        assert items[0]["is_capture"] is True
        assert items[0]["is_owner"] is True

    def test_add_root_items_with_individual_files(self):
        """Test adding root items with individual files."""
        # Delete the capture so we only have individual files
        self.capture.delete()

        items = []
        add_root_items(self.user, items)

        # Should have one file item
        assert len(items) == 1
        assert items[0]["type"] == "file"
        assert items[0]["name"] == "test.txt"

    def test_add_root_items_empty(self):
        """Test adding root items with no captures or files."""
        # Delete both capture and file
        self.capture.delete()
        self.file.delete()

        items = []
        add_root_items(self.user, items)

        # Should have no items
        assert len(items) == 0


class AddCaptureFilesTestCase(TestCase):
    """Test the extracted add_capture_files function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",  # noqa: S106
        )
        self.capture = Capture.objects.create(
            owner=self.user,
            name="Test Capture",
            uuid="123e4567-e89b-12d3-a456-426614174000",
            top_level_dir="/test/capture",
        )
        self.file1 = File.objects.create(
            owner=self.user,
            name="test1.txt",
            uuid="456e7890-e89b-12d3-a456-426614174000",
            directory="/test/capture/level1",
            capture=self.capture,
            is_deleted=False,
        )
        self.file2 = File.objects.create(
            owner=self.user,
            name="test2.txt",
            uuid="789e0123-e89b-12d3-a456-426614174000",
            directory="/test/capture/level1/subdir",
            capture=self.capture,
            is_deleted=False,
        )

    def test_add_capture_files_root_level(self):
        """Test adding capture files at root level."""
        items = []
        add_capture_files(self.user, items, str(self.capture.uuid), "")

        # Should have one file at root level
        assert len(items) == 1
        assert items[0]["type"] == "file"
        assert items[0]["name"] == "test1.txt"

    def test_add_capture_files_with_subpath(self):
        """Test adding capture files with a specific subpath."""
        items = []
        add_capture_files(self.user, items, str(self.capture.uuid), "level1")

        # Should have one file and one directory
        expected_items = 2
        assert len(items) == expected_items

        # Check directory item
        dir_item = next(item for item in items if item["type"] == "directory")
        assert dir_item["name"] == "subdir"
        assert dir_item["is_capture"] is False

        # Check file item
        file_item = next(item for item in items if item["type"] == "file")
        assert file_item["name"] == "test1.txt"

    def test_add_capture_files_shared_capture(self):
        """Test adding files from a shared capture."""
        # Create another user and share the capture
        other_user = User.objects.create_user(
            email="other@example.com",
            password="testpass123",  # noqa: S106
        )

        # Create a mock request object
        mock_request = Mock()
        mock_request.user = other_user

        items = []
        add_capture_files(mock_request, items, str(self.capture.uuid), "")

        # Should have one file at root level
        assert len(items) == 1
        assert items[0]["type"] == "file"
        assert items[0]["name"] == "test1.txt"

    def test_add_capture_files_invalid_capture(self):
        """Test adding files with invalid capture UUID."""
        items = []
        add_capture_files(self.user, items, "invalid-uuid", "")

        # Should have no items
        assert len(items) == 0


class AddSharedItemsTestCase(TestCase):
    """Test the extracted add_shared_items function."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",  # noqa: S106
        )
        test_password = "testpass123"  # noqa: S105
        self.owner = User.objects.create_user(
            email="owner@example.com", password=test_password
        )
        self.capture = Capture.objects.create(
            owner=self.owner,
            name="Shared Capture",
            uuid="123e4567-e89b-12d3-a456-426614174000",
        )
        self.shared_permission = UserSharePermission.objects.create(
            owner=self.owner,
            item_uuid=self.capture.uuid,
            item_type=ItemType.CAPTURE,
            shared_with=self.user,
            is_deleted=False,
            is_enabled=True,
        )

    def test_add_shared_items_with_shared_captures(self):
        """Test adding shared items with shared captures."""
        items = []
        add_shared_items(self.user, items)

        # Should have one shared capture
        assert len(items) == 1
        assert items[0]["type"] == "directory"
        assert items[0]["name"] == "Shared Capture"
        assert items[0]["is_capture"] is True
        assert items[0]["is_shared"] is True
        assert items[0]["is_owner"] is False
        assert items[0]["shared_by"] == "owner@example.com"

    def test_add_shared_items_no_shared_items(self):
        """Test adding shared items when user has no shared items."""
        # Delete the shared permission
        self.shared_permission.delete()

        items = []
        add_shared_items(self.user, items)

        # Should have no items
        assert len(items) == 0

    def test_add_shared_items_disabled_permission(self):
        """Test adding shared items with disabled permission."""
        # Disable the shared permission
        self.shared_permission.is_enabled = False
        self.shared_permission.save()

        items = []
        add_shared_items(self.user, items)

        # Should have no items
        assert len(items) == 0

    def test_add_shared_items_deleted_permission(self):
        """Test adding shared items with deleted permission."""
        # Mark the shared permission as deleted
        self.shared_permission.is_deleted = True
        self.shared_permission.save()

        items = []
        add_shared_items(self.user, items)

        # Should have no items
        assert len(items) == 0
