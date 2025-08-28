"""
Test for the extracted build_breadcrumbs function.
"""

from django.test import TestCase

from sds_gateway.api_methods.models import Capture
from sds_gateway.users.files_utils import build_breadcrumbs
from sds_gateway.users.models import User


class BuildBreadcrumbsTestCase(TestCase):
    """Test the extracted build_breadcrumbs function."""

    def setUp(self):
        """Set up test data."""
        self.capture = Capture.objects.create(
            owner=User.objects.create_user(
                email="owner@example.com",
                password="testpass123",  # noqa: S106
            ),
            name="Test Capture",
            uuid="123e4567-e89b-12d3-a456-426614174000",
        )

    def test_build_breadcrumbs_root_path(self):
        """Test building breadcrumbs for root path."""
        breadcrumbs = build_breadcrumbs("/", "test@example.com")

        # Should have no breadcrumbs for root
        assert len(breadcrumbs) == 0

    def test_build_breadcrumbs_simple_path(self):
        """Test building breadcrumbs for simple path."""
        breadcrumbs = build_breadcrumbs(
            "/captures/123e4567-e89b-12d3-a456-426614174000", "test@example.com"
        )

        # Should have one breadcrumb for the capture
        assert len(breadcrumbs) == 1
        assert breadcrumbs[0]["name"] == "Test Capture"
        assert (
            breadcrumbs[0]["path"] == "/captures/123e4567-e89b-12d3-a456-426614174000"
        )

    def test_build_breadcrumbs_nested_path(self):
        """Test building breadcrumbs for nested path."""
        breadcrumbs = build_breadcrumbs(
            "/captures/123e4567-e89b-12d3-a456-426614174000/subdir/nested",
            "test@example.com",
        )

        # Should have three breadcrumbs: capture, subdir, nested
        expected_breadcrumbs = 3
        assert len(breadcrumbs) == expected_breadcrumbs
        assert breadcrumbs[0]["name"] == "Test Capture"
        assert breadcrumbs[1]["name"] == "subdir"
        assert breadcrumbs[2]["name"] == "nested"

    def test_build_breadcrumbs_skips_technical_segments(self):
        """Test that breadcrumbs skip technical segments."""
        breadcrumbs = build_breadcrumbs(
            "/files/test@example.com/captures/123e4567-e89b-12d3-a456-426614174000",
            "test@example.com",
        )

        # Should only have the capture, skipping 'files' and user email
        assert len(breadcrumbs) == 1
        assert breadcrumbs[0]["name"] == "Test Capture"

    def test_build_breadcrumbs_invalid_uuid(self):
        """Test building breadcrumbs with invalid UUID."""
        breadcrumbs = build_breadcrumbs(
            "/captures/invalid-uuid/subdir", "test@example.com"
        )

        # Should have two breadcrumbs with raw UUID
        expected_breadcrumbs = 2
        assert len(breadcrumbs) == expected_breadcrumbs
        assert breadcrumbs[0]["name"] == "invalid-uuid"
        assert breadcrumbs[1]["name"] == "subdir"
