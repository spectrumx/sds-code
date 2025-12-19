"""Tests for user files utility functions.

This module tests the utility functions in files_utils.py that handle
user file navigation, directory structure building, and modified date calculations.
"""

# pyright: reportPrivateUsage=false

import uuid
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.tests.factories import FileFactory
from sds_gateway.users.files_utils import DirItemParams
from sds_gateway.users.files_utils import _add_child_files
from sds_gateway.users.files_utils import _add_user_file_directories
from sds_gateway.users.files_utils import _calculate_dir_modified_date
from sds_gateway.users.files_utils import _filter_files_by_subpath
from sds_gateway.users.files_utils import _get_relative_directory
from sds_gateway.users.files_utils import _normalize_path
from sds_gateway.users.files_utils import add_capture_files
from sds_gateway.users.files_utils import add_root_items
from sds_gateway.users.files_utils import add_shared_items
from sds_gateway.users.files_utils import add_user_files
from sds_gateway.users.files_utils import build_breadcrumbs
from sds_gateway.users.files_utils import format_modified
from sds_gateway.users.files_utils import make_dir_item
from sds_gateway.users.files_utils import make_file_item
from sds_gateway.users.navigation_models import NavigationContext
from sds_gateway.users.navigation_models import NavigationType
from sds_gateway.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestNormalizePath:
    """Tests for _normalize_path function."""

    def test_removes_leading_slash(self):
        assert _normalize_path("/files/test") == "files/test"

    def test_removes_trailing_slash(self):
        assert _normalize_path("files/test/") == "files/test"

    def test_removes_both_slashes(self):
        assert _normalize_path("/files/test/") == "files/test"

    def test_empty_string(self):
        assert _normalize_path("") == ""

    def test_single_slash(self):
        assert _normalize_path("/") == ""

    def test_no_slashes(self):
        assert _normalize_path("files") == "files"


class TestFormatModified:
    """Tests for format_modified function."""

    def test_formats_datetime(self):
        dt = timezone.datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        result = format_modified(dt)
        assert result == "2024-01-15 10:30"

    def test_returns_na_for_none(self):
        assert format_modified(None) == "N/A"


class TestGetRelativeDirectory:
    """Tests for _get_relative_directory function."""

    def test_relative_to_user_root(self):
        file_obj = MagicMock()
        file_obj.directory = "/files/user@example.com/subdir"
        user_root = "files/user@example.com"

        result = _get_relative_directory(file_obj, "", user_root)
        assert result == "subdir"

    def test_relative_to_capture_root(self):
        file_obj = MagicMock()
        file_obj.directory = "/files/user@example.com/capture1/data"
        capture_root = "files/user@example.com/capture1"
        user_root = "files/user@example.com"

        result = _get_relative_directory(file_obj, capture_root, user_root)
        assert result == "data"

    def test_file_at_root_level(self):
        file_obj = MagicMock()
        file_obj.directory = "/files/user@example.com"
        user_root = "files/user@example.com"

        result = _get_relative_directory(file_obj, "", user_root)
        assert result == ""


class TestCalculateDirModifiedDate:
    """Tests for _calculate_dir_modified_date function."""

    def test_returns_none_for_empty_files(self):
        result = _calculate_dir_modified_date(
            "subdir", "", None, "files/user@example.com"
        )
        assert result is None

    def test_returns_none_for_no_matching_files(self):
        file_obj = MagicMock()
        file_obj.directory = "/files/user@example.com/other_dir"
        file_obj.updated_at = timezone.now()

        result = _calculate_dir_modified_date(
            "subdir", "", [file_obj], "files/user@example.com"
        )
        assert result is None

    def test_returns_most_recent_date_for_files_directly_in_dir(self):
        now = timezone.now()
        older = now - timedelta(hours=1)

        file1 = MagicMock()
        file1.directory = "/files/user@example.com/subdir"
        file1.updated_at = older

        file2 = MagicMock()
        file2.directory = "/files/user@example.com/subdir"
        file2.updated_at = now

        result = _calculate_dir_modified_date(
            "subdir", "", [file1, file2], "files/user@example.com"
        )
        assert result == now

    def test_returns_most_recent_date_for_files_in_subdirs(self):
        now = timezone.now()
        older = now - timedelta(hours=1)

        file1 = MagicMock()
        file1.directory = "/files/user@example.com/subdir/nested"
        file1.updated_at = now

        file2 = MagicMock()
        file2.directory = "/files/user@example.com/subdir"
        file2.updated_at = older

        result = _calculate_dir_modified_date(
            "subdir", "", [file1, file2], "files/user@example.com"
        )
        assert result == now

    def test_with_current_subpath(self):
        now = timezone.now()

        file_obj = MagicMock()
        file_obj.directory = "/files/user@example.com/parent/child"
        file_obj.updated_at = now

        result = _calculate_dir_modified_date(
            "child", "parent", [file_obj], "files/user@example.com"
        )
        assert result == now


class TestFilterFilesBySubpath:
    """Tests for _filter_files_by_subpath function."""

    def test_empty_files_returns_empty(self):
        child_files, child_dirs = _filter_files_by_subpath(
            [], "", "files/user@example.com"
        )
        assert child_files == []
        assert child_dirs == set()

    def test_files_at_root_level(self):
        file_obj = MagicMock()
        file_obj.directory = "/files/user@example.com"

        child_files, child_dirs = _filter_files_by_subpath(
            [file_obj], "", "files/user@example.com"
        )
        assert len(child_files) == 1
        assert child_dirs == set()

    def test_collects_child_directories(self):
        file_obj = MagicMock()
        file_obj.directory = "/files/user@example.com/subdir/nested"

        child_files, child_dirs = _filter_files_by_subpath(
            [file_obj], "", "files/user@example.com"
        )
        assert child_files == []
        assert "subdir" in child_dirs

    def test_filters_by_subpath(self):
        # File directly in parent/child directory
        file_in_child = MagicMock()
        file_in_child.directory = "/files/user@example.com/parent/child"

        # File in a deeper nested directory
        file_in_nested = MagicMock()
        file_in_nested.directory = "/files/user@example.com/parent/child/deep"

        file_outside = MagicMock()
        file_outside.directory = "/files/user@example.com/other"

        _child_files, child_dirs = _filter_files_by_subpath(
            [file_in_child, file_in_nested, file_outside],
            "parent",
            "files/user@example.com",
        )
        assert "child" in child_dirs, "child directory should be included"
        assert "other" not in child_dirs, "other directory should be excluded"


class TestMakeDirItem:
    """Tests for make_dir_item function."""

    def test_creates_directory_item(self):
        test_uuid = str(uuid.uuid4())
        params = DirItemParams(
            name="test_dir",
            path="/files/test_dir",
            uuid=test_uuid,
            is_capture=False,
            is_owner=True,
            capture_uuid="",
            modified_at_display="2024-01-15 10:30",
            shared_by="",
        )
        item = make_dir_item(params)

        assert item.name == "test_dir"
        assert item.path == "/files/test_dir"
        assert str(item.uuid) == test_uuid
        assert item.is_capture is False
        assert item.modified_at == "2024-01-15 10:30"

    def test_creates_directory_item_with_empty_uuid(self):
        """Test that empty UUID is allowed for non-capture directories."""
        params = DirItemParams(
            name="test_dir",
            path="/files/test_dir",
            uuid="",
            is_capture=False,
            is_owner=True,
            capture_uuid="",
            modified_at_display="2024-01-15 10:30",
            shared_by="",
        )
        item = make_dir_item(params)

        assert item.name == "test_dir"
        assert item.uuid == ""

    def test_creates_capture_directory_item(self):
        test_uuid = str(uuid.uuid4())
        params = DirItemParams(
            name="My Capture",
            path=f"/captures/{test_uuid}",
            uuid=test_uuid,
            is_capture=True,
            is_owner=True,
            capture_uuid=test_uuid,
            modified_at_display="2024-01-15 10:30",
            shared_by="",
        )
        item = make_dir_item(params)

        assert item.is_capture is True


class TestMakeFileItem:
    """Tests for make_file_item function."""

    def test_creates_file_item(self):
        user = UserFactory()
        file_obj = FileFactory(owner=user, name="test.h5")

        item = make_file_item(file_obj=file_obj, capture_uuid="", is_shared=False)

        assert item.name == "test.h5"
        assert item.is_shared is False
        assert item.capture_uuid == ""

    def test_creates_shared_file_item(self):
        user = UserFactory()
        file_obj = FileFactory(owner=user, name="shared.h5")
        test_capture_uuid = str(uuid.uuid4())

        item = make_file_item(
            file_obj=file_obj,
            capture_uuid=test_capture_uuid,
            is_shared=True,
            shared_by="owner@example.com",
        )

        assert item.is_shared is True
        assert str(item.capture_uuid) == test_capture_uuid
        assert item.shared_by == "owner@example.com"


class TestAddUserFileDirectories:
    """Tests for _add_user_file_directories function."""

    def test_empty_dirs_returns_empty(self):
        items = _add_user_file_directories(set(), "")
        assert items == []

    def test_creates_directory_items(self):
        dirs = {"dir1", "dir2"}
        items = _add_user_file_directories(dirs, "")

        assert len(items) == len(dirs)
        names = [item.name for item in items]
        assert "dir1" in names
        assert "dir2" in names

    def test_builds_correct_paths(self):
        items = _add_user_file_directories({"subdir"}, "parent")

        assert len(items) == 1
        assert items[0].path == "/files/parent/subdir"

    def test_calculates_modified_date(self):
        now = timezone.now()
        file_obj = MagicMock()
        file_obj.directory = "/files/user@example.com/subdir"
        file_obj.updated_at = now

        items = _add_user_file_directories(
            {"subdir"},
            "",
            user_files=[file_obj],
            user_root="files/user@example.com",
        )

        assert len(items) == 1
        assert items[0].modified_at != "N/A"


class TestAddChildFiles:
    """Tests for _add_child_files function."""

    def test_empty_files_returns_empty(self):
        items = _add_child_files([], "")
        assert items == []

    def test_creates_file_items(self):
        user = UserFactory()
        file1 = FileFactory(owner=user, name="file1.h5")
        file2 = FileFactory(owner=user, name="file2.h5")
        test_capture_uuid = str(uuid.uuid4())

        files = [file1, file2]
        items = _add_child_files(files, test_capture_uuid)

        assert len(items) == len(files), "Should create items for all files"

    def test_sorts_files_alphabetically(self):
        user = UserFactory()
        file_z = FileFactory(owner=user, name="zebra.h5")
        file_a = FileFactory(owner=user, name="alpha.h5")
        test_capture_uuid = str(uuid.uuid4())

        items = _add_child_files([file_z, file_a], test_capture_uuid)

        assert items[0].name == "alpha.h5"
        assert items[1].name == "zebra.h5"


class TestBuildBreadcrumbs:
    """Tests for build_breadcrumbs function."""

    def test_root_returns_empty(self):
        breadcrumbs = build_breadcrumbs("/", "user@example.com")
        assert breadcrumbs == []

    def test_skips_files_segment(self):
        breadcrumbs = build_breadcrumbs("/files/subdir", "user@example.com")
        # Should skip "files" segment
        names = [b["name"] for b in breadcrumbs]
        assert "files" not in names

    def test_skips_user_email(self):
        breadcrumbs = build_breadcrumbs(
            "/files/user@example.com/subdir", "user@example.com"
        )
        names = [b["name"] for b in breadcrumbs]
        assert "user@example.com" not in names
        assert "subdir" in names

    def test_builds_correct_paths_with_capture(self):
        user = UserFactory()
        capture = Capture.objects.create(
            owner=user,
            name="Breadcrumb Capture",
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            top_level_dir="/breadcrumb",
        )

        breadcrumbs = build_breadcrumbs(f"/captures/{capture.uuid}/subdir", user.email)

        expected_min_breadcrumbs = 2
        assert len(breadcrumbs) >= expected_min_breadcrumbs
        # First breadcrumb should be capture
        assert breadcrumbs[0]["name"] == "Breadcrumb Capture"
        # Last breadcrumb should have full path with subdir
        last = breadcrumbs[-1]
        assert "subdir" in last["path"]


class TestAddUserFiles:
    """Tests for add_user_files function."""

    def test_returns_empty_for_user_with_no_files(self):
        user = UserFactory()
        request = MagicMock()
        request.user = user

        items = add_user_files(request, "")

        assert items == []

    def test_returns_files_not_in_captures(self):
        user = UserFactory()
        # Create a file not associated with any capture
        _file_obj = FileFactory(
            owner=user,
            name="standalone.h5",
            directory=f"/files/{user.email}",
        )

        request = MagicMock()
        request.user = user

        items = add_user_files(request, "")

        # Should find the standalone file
        file_names = [item.name for item in items if hasattr(item, "name")]
        assert "standalone.h5" in file_names

    def test_filters_by_subpath(self):
        user = UserFactory()
        # Create files in different directories
        FileFactory(
            owner=user,
            name="root_file.h5",
            directory=f"/files/{user.email}",
        )
        FileFactory(
            owner=user,
            name="subdir_file.h5",
            directory=f"/files/{user.email}/subdir",
        )

        request = MagicMock()
        request.user = user

        # Request files in subdir
        items = add_user_files(request, "subdir")

        file_names = [item.name for item in items if hasattr(item, "name")]
        assert "subdir_file.h5" in file_names
        assert "root_file.h5" not in file_names


class TestAddRootItems:
    """Tests for add_root_items function."""

    def test_returns_empty_for_user_with_no_content(self):
        user = UserFactory()
        request = MagicMock()
        request.user = user

        items = add_root_items(request)

        # May return empty or just system items
        assert isinstance(items, list)

    def test_includes_user_captures(self):
        user = UserFactory()
        _capture = Capture.objects.create(
            owner=user,
            name="Test Capture",
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            top_level_dir="/test",
        )

        request = MagicMock()
        request.user = user

        items = add_root_items(request)

        # Should find the capture as a directory item
        capture_names = [
            item.name
            for item in items
            if hasattr(item, "is_capture") and item.is_capture
        ]
        assert "Test Capture" in capture_names


class TestAddSharedItems:
    """Tests for add_shared_items function."""

    def test_returns_empty_for_user_with_no_shared_items(self):
        user = UserFactory()
        request = MagicMock()
        request.user = user

        items = add_shared_items(request)

        assert items == []

    def test_includes_shared_captures(self):
        owner = UserFactory()
        shared_user = UserFactory()

        # Create a capture owned by owner
        capture = Capture.objects.create(
            owner=owner,
            name="Shared Capture",
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            top_level_dir="/shared",
        )

        # Share with shared_user
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=shared_user,
            item_type=ItemType.CAPTURE,
            item_uuid=capture.uuid,
            is_enabled=True,
        )

        request = MagicMock()
        request.user = shared_user

        items = add_shared_items(request)

        # Should find the shared capture
        shared_names = [
            item.name for item in items if hasattr(item, "is_shared") and item.is_shared
        ]
        assert "Shared Capture" in shared_names

    def test_excludes_own_captures(self):
        user = UserFactory()

        # Create a capture owned by user
        capture = Capture.objects.create(
            owner=user,
            name="Own Capture",
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            top_level_dir="/own",
        )

        # Create share permission pointing to own capture (edge case)
        UserSharePermission.objects.create(
            owner=user,
            shared_with=user,
            item_type=ItemType.CAPTURE,
            item_uuid=capture.uuid,
            is_enabled=True,
        )

        request = MagicMock()
        request.user = user

        items = add_shared_items(request)

        # Should NOT include own capture in shared items
        shared_names = [item.name for item in items]
        assert "Own Capture" not in shared_names


class TestAddCaptureFiles:
    """Tests for add_capture_files function."""

    def test_returns_empty_for_nonexistent_capture(self):
        user = UserFactory()
        request = MagicMock()
        request.user = user

        items = add_capture_files(request, str(uuid.uuid4()))

        assert items == []

    def test_returns_empty_for_capture_without_access(self):
        owner = UserFactory()
        other_user = UserFactory()

        capture = Capture.objects.create(
            owner=owner,
            name="Private Capture",
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            top_level_dir="/private",
        )

        request = MagicMock()
        request.user = other_user

        items = add_capture_files(request, str(capture.uuid))

        assert items == []

    def test_returns_files_for_owned_capture(self):
        """Test that capture files are returned for owned captures."""
        user = UserFactory()
        capture = Capture.objects.create(
            owner=user,
            name="My Capture",
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            top_level_dir="/my-capture",
        )

        # Create a file associated with the capture using FileFactory with directory
        FileFactory(
            owner=user,
            name="capture_file.h5",
            directory=f"/files/{user.email}/my-capture/ch0",
            capture=capture,
        )

        request = MagicMock()
        request.user = user

        # Verify capture can be retrieved
        items = add_capture_files(request, str(capture.uuid))
        # The file should be in a subdirectory, so we should see "ch0" directory
        assert len(items) > 0, "Expected at least one item (directory or file)"

    def test_returns_files_for_shared_capture(self):
        """Test that shared captures are accessible to shared users."""
        owner = UserFactory()
        shared_user = UserFactory()

        capture = Capture.objects.create(
            owner=owner,
            name="Shared Capture",
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            top_level_dir="/shared",
        )

        # Create a file associated with the capture
        FileFactory(
            owner=owner,
            name="shared_file.h5",
            directory=f"/files/{owner.email}/shared/ch0",
            capture=capture,
        )

        # Share with shared_user
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=shared_user,
            item_type=ItemType.CAPTURE,
            item_uuid=capture.uuid,
            is_enabled=True,
        )

        request = MagicMock()
        request.user = shared_user

        # Verify shared user can access capture files
        items = add_capture_files(request, str(capture.uuid))
        # Should return items (either the file or a directory containing it)
        assert len(items) > 0, "Shared user should see capture contents"


class TestNavigationContext:
    """Tests for NavigationContext parsing and path handling."""

    def test_root_path_returns_root_type(self):
        nav = NavigationContext.from_path("/")
        assert nav.type == NavigationType.ROOT
        assert nav.capture_uuid is None
        assert nav.subpath == ""

    def test_captures_path_parses_uuid(self):
        test_uuid = str(uuid.uuid4())
        nav = NavigationContext.from_path(f"/captures/{test_uuid}")
        assert nav.type == NavigationType.CAPTURE
        assert nav.capture_uuid == test_uuid
        assert nav.subpath == ""

    def test_captures_path_with_subpath(self):
        test_uuid = str(uuid.uuid4())
        nav = NavigationContext.from_path(f"/captures/{test_uuid}/data/nested")
        assert nav.type == NavigationType.CAPTURE
        assert nav.capture_uuid == test_uuid
        assert nav.subpath == "data/nested"

    def test_files_path_returns_user_files_type(self):
        nav = NavigationContext.from_path("/files/subdir")
        assert nav.type == NavigationType.USER_FILES
        assert nav.subpath == "subdir"

    def test_files_path_with_nested_subpath(self):
        nav = NavigationContext.from_path("/files/parent/child/grandchild")
        assert nav.type == NavigationType.USER_FILES
        assert nav.subpath == "parent/child/grandchild"

    def test_to_path_reconstructs_root(self):
        nav = NavigationContext(type=NavigationType.ROOT)
        assert nav.to_path() == "/"

    def test_to_path_reconstructs_capture_path(self):
        test_uuid = str(uuid.uuid4())
        nav = NavigationContext(
            type=NavigationType.CAPTURE,
            capture_uuid=test_uuid,
            subpath="data",
        )
        assert nav.to_path() == f"/captures/{test_uuid}/data"

    def test_to_path_reconstructs_user_files_path(self):
        nav = NavigationContext(
            type=NavigationType.USER_FILES,
            subpath="my-dir/nested",
        )
        assert nav.to_path() == "/files/my-dir/nested"


class TestFilesViewNavigation:
    """Integration tests for FilesView navigation routing."""

    def test_root_navigation_returns_root_items(self):
        """Test that root path returns captures and user files."""
        user = UserFactory()

        # Create a capture
        Capture.objects.create(
            owner=user,
            name="Test Capture",
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            top_level_dir="/test",
        )

        request = MagicMock()
        request.user = user
        request.GET = {"dir": "/"}

        # Parse navigation context
        nav_context = NavigationContext.from_path("/")
        assert nav_context.type == NavigationType.ROOT

        # Verify root items include the capture
        items = add_root_items(request)
        capture_names = [
            item.name
            for item in items
            if hasattr(item, "is_capture") and item.is_capture
        ]
        assert "Test Capture" in capture_names

    def test_user_files_navigation_returns_user_files(self):
        """Test that /files/subdir path returns user files in that directory."""
        user = UserFactory()

        # Create a file in a subdirectory
        FileFactory(
            owner=user,
            name="nested_file.h5",
            directory=f"/files/{user.email}/mysubdir",
        )

        request = MagicMock()
        request.user = user

        # Parse navigation context
        nav_context = NavigationContext.from_path("/files/mysubdir")
        assert nav_context.type == NavigationType.USER_FILES
        assert nav_context.subpath == "mysubdir"

        # Verify user files are returned
        items = add_user_files(request, subpath=nav_context.subpath)
        file_names = [item.name for item in items if hasattr(item, "name")]
        assert "nested_file.h5" in file_names

    def test_capture_navigation_returns_capture_files(self):
        """Test that /captures/<uuid> path returns capture files."""
        user = UserFactory()

        capture = Capture.objects.create(
            owner=user,
            name="Nav Test Capture",
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            top_level_dir="/navtest",
        )

        # Create a file in the capture's subdirectory
        FileFactory(
            owner=user,
            name="capture_data.h5",
            directory=f"/files/{user.email}/navtest/ch0",
            capture=capture,
        )

        request = MagicMock()
        request.user = user

        # Parse navigation context
        nav_context = NavigationContext.from_path(f"/captures/{capture.uuid}")
        assert nav_context.type == NavigationType.CAPTURE
        assert nav_context.capture_uuid == str(capture.uuid)

        # Verify capture files are returned
        items = add_capture_files(request, nav_context.capture_uuid)
        assert len(items) > 0, "Expected capture contents to be returned"

    def test_nested_user_files_navigation(self):
        """Test navigation through nested user file directories."""
        user = UserFactory()

        # Create files at different nesting levels
        FileFactory(
            owner=user,
            name="level1_file.h5",
            directory=f"/files/{user.email}/parent",
        )
        FileFactory(
            owner=user,
            name="level2_file.h5",
            directory=f"/files/{user.email}/parent/child",
        )

        request = MagicMock()
        request.user = user

        # Navigate to parent - should see level1_file and child directory
        nav_context = NavigationContext.from_path("/files/parent")
        items = add_user_files(request, subpath=nav_context.subpath)

        item_names = [item.name for item in items]
        assert "level1_file.h5" in item_names
        assert "child" in item_names  # Directory should appear

        # Navigate to parent/child - should only see level2_file
        nav_context = NavigationContext.from_path("/files/parent/child")
        items = add_user_files(request, subpath=nav_context.subpath)

        item_names = [item.name for item in items]
        assert "level2_file.h5" in item_names
        assert "level1_file.h5" not in item_names
