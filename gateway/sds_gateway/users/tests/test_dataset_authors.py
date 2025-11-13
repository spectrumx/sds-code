"""Tests for dataset authors validation in DatasetInfoForm."""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from sds_gateway.users.forms import DatasetInfoForm

User = get_user_model()


class TestDatasetAuthors(TestCase):
    """Test dataset authors validation functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",  # noqa: S106
            name="Test User",
            is_approved=True,
        )

    def test_new_format_single_author_with_orcid(self):
        """Test that new dict format with ORCID ID works correctly."""
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": '[{"name": "John Doe", "orcid_id": "0000-0001-2345-6789"}]',
            "status": "draft",
        }
        form = DatasetInfoForm(data=form_data, user=self.user)
        assert form.is_valid()
        cleaned_authors = json.loads(form.cleaned_data["authors"])
        assert len(cleaned_authors) == 1
        assert cleaned_authors[0]["name"] == "John Doe"
        assert cleaned_authors[0]["orcid_id"] == "0000-0001-2345-6789"

    def test_new_format_multiple_authors(self):
        """Test that new dict format with multiple authors works correctly."""
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": json.dumps(
                [
                    {"name": "John Doe", "orcid_id": "0000-0001-2345-6789"},
                    {"name": "Jane Smith", "orcid_id": "0000-0002-3456-7890"},
                    {"name": "Bob Johnson", "orcid_id": ""},
                ]
            ),
            "status": "draft",
        }
        form = DatasetInfoForm(data=form_data, user=self.user)
        assert form.is_valid()
        cleaned_authors = json.loads(form.cleaned_data["authors"])
        expected_author_count = 3
        assert len(cleaned_authors) == expected_author_count
        assert cleaned_authors[0]["name"] == "John Doe"
        assert cleaned_authors[1]["name"] == "Jane Smith"
        assert cleaned_authors[2]["name"] == "Bob Johnson"
        assert cleaned_authors[2]["orcid_id"] == ""

    def test_new_format_author_without_orcid(self):
        """Test that new dict format works with empty ORCID ID."""
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": '[{"name": "John Doe", "orcid_id": ""}]',
            "status": "draft",
        }
        form = DatasetInfoForm(data=form_data, user=self.user)
        assert form.is_valid()
        cleaned_authors = json.loads(form.cleaned_data["authors"])
        assert len(cleaned_authors) == 1
        assert cleaned_authors[0]["name"] == "John Doe"
        assert cleaned_authors[0]["orcid_id"] == ""

    def test_old_format_string_rejected(self):
        """Test that old string format is rejected with user-friendly error."""
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": '["John Doe", "Jane Smith"]',
            "status": "draft",
        }
        form = DatasetInfoForm(data=form_data, user=self.user)
        assert not form.is_valid()
        assert "authors" in form.errors
        error_message = str(form.errors["authors"][0])
        assert "Database error encountered" in error_message
        assert "Please contact support" in error_message

    def test_old_format_string_logs_error_with_dataset_uuid(self):
        """Test that old string format logs error with dataset UUID when provided."""
        dataset_uuid = "123e4567-e89b-12d3-a456-426614174000"
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": '["John Doe"]',
            "status": "draft",
        }
        with patch("sds_gateway.users.forms.logger") as mock_logger:
            form = DatasetInfoForm(
                data=form_data, user=self.user, dataset_uuid=dataset_uuid
            )
            form.is_valid()  # Trigger validation
            # Verify logger.error was called
            assert mock_logger.error.called
            # Verify the log message contains the dataset UUID
            call_args = mock_logger.error.call_args[0][0]
            assert dataset_uuid in call_args
            assert "migration 0017 failed" in call_args

    def test_old_format_string_logs_error_without_dataset_uuid(self):
        """Test old string format logs error with 'unknown' when UUID not provided."""
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": '["John Doe"]',
            "status": "draft",
        }
        with patch("sds_gateway.users.forms.logger") as mock_logger:
            form = DatasetInfoForm(data=form_data, user=self.user)
            form.is_valid()  # Trigger validation
            # Verify logger.error was called
            assert mock_logger.error.called
            # Verify the log message contains 'unknown' for UUID
            call_args = mock_logger.error.call_args[0][0]
            assert "unknown" in call_args
            assert "migration 0017 failed" in call_args

    def test_empty_authors_list_rejected(self):
        """Test that empty authors list is rejected."""
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": "[]",
            "status": "draft",
        }
        form = DatasetInfoForm(data=form_data, user=self.user)
        assert not form.is_valid()
        assert "authors" in form.errors
        error_message = str(form.errors["authors"][0])
        assert "At least one author is required" in error_message

    def test_invalid_json_rejected(self):
        """Test that invalid JSON in authors field is rejected."""
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": "not valid json",
            "status": "draft",
        }
        form = DatasetInfoForm(data=form_data, user=self.user)
        assert not form.is_valid()
        assert "authors" in form.errors
        error_message = str(form.errors["authors"][0])
        assert "Invalid authors format" in error_message

    def test_authors_not_list_rejected(self):
        """Test that non-list authors format is rejected."""
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": '{"name": "John Doe"}',
            "status": "draft",
        }
        form = DatasetInfoForm(data=form_data, user=self.user)
        assert not form.is_valid()
        assert "authors" in form.errors
        error_message = str(form.errors["authors"][0])
        assert "Authors must be a list" in error_message

    def test_author_with_empty_name_skipped(self):
        """Test that authors with empty names are skipped."""
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": json.dumps(
                [
                    {"name": "John Doe", "orcid_id": "0000-0001-2345-6789"},
                    {"name": "", "orcid_id": "0000-0002-3456-7890"},
                    {"name": "   ", "orcid_id": ""},
                    {"name": "Jane Smith", "orcid_id": ""},
                ]
            ),
            "status": "draft",
        }
        form = DatasetInfoForm(data=form_data, user=self.user)
        assert form.is_valid()
        cleaned_authors = json.loads(form.cleaned_data["authors"])
        # Empty names should be skipped
        expected_author_count = 2
        assert len(cleaned_authors) == expected_author_count
        assert cleaned_authors[0]["name"] == "John Doe"
        assert cleaned_authors[1]["name"] == "Jane Smith"

    def test_author_name_whitespace_stripped(self):
        """Test that author names have whitespace stripped."""
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": '[{"name": "  John Doe  ", "orcid_id": "0000-0001-2345-6789"}]',
            "status": "draft",
        }
        form = DatasetInfoForm(data=form_data, user=self.user)
        assert form.is_valid()
        cleaned_authors = json.loads(form.cleaned_data["authors"])
        assert cleaned_authors[0]["name"] == "John Doe"

    def test_author_orcid_whitespace_stripped(self):
        """Test that ORCID IDs have whitespace stripped."""
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": '[{"name": "John Doe", "orcid_id": "  0000-0001-2345-6789  "}]',
            "status": "draft",
        }
        form = DatasetInfoForm(data=form_data, user=self.user)
        assert form.is_valid()
        cleaned_authors = json.loads(form.cleaned_data["authors"])
        assert cleaned_authors[0]["orcid_id"] == "0000-0001-2345-6789"

    def test_author_missing_name_key(self):
        """Test that authors missing 'name' key are skipped."""
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": json.dumps(
                [
                    {"name": "John Doe", "orcid_id": "0000-0001-2345-6789"},
                    {"orcid_id": "0000-0002-3456-7890"},
                    {"name": "Jane Smith"},
                ]
            ),
            "status": "draft",
        }
        form = DatasetInfoForm(data=form_data, user=self.user)
        assert form.is_valid()
        cleaned_authors = json.loads(form.cleaned_data["authors"])
        # Only authors with valid names should be included
        expected_author_count = 2
        assert len(cleaned_authors) == expected_author_count
        assert cleaned_authors[0]["name"] == "John Doe"
        assert cleaned_authors[1]["name"] == "Jane Smith"

    def test_all_authors_empty_names_rejected(self):
        """Test that if all authors have empty names, validation fails."""
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": json.dumps(
                [
                    {"name": "", "orcid_id": "0000-0001-2345-6789"},
                    {"name": "   ", "orcid_id": ""},
                ]
            ),
            "status": "draft",
        }
        form = DatasetInfoForm(data=form_data, user=self.user)
        assert not form.is_valid()
        assert "authors" in form.errors
        error_message = str(form.errors["authors"][0])
        assert "At least one valid author is required" in error_message

    def test_mixed_old_and_new_format_rejected(self):
        """Test that mixing old string format with new dict format is rejected."""
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": json.dumps(
                [
                    {"name": "John Doe", "orcid_id": "0000-0001-2345-6789"},
                    "Jane Smith",  # Old string format
                ]
            ),
            "status": "draft",
        }
        form = DatasetInfoForm(data=form_data, user=self.user)
        assert not form.is_valid()
        assert "authors" in form.errors
        error_message = str(form.errors["authors"][0])
        assert "Database error encountered" in error_message

    def test_author_name_minimum_length_validation(self):
        """Test that author names respect minimum length requirement."""
        # MIN_AUTHOR_NAME_LENGTH is 0, so this test verifies the validation logic
        # If the constant changes, this test should be updated
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "authors": '[{"name": "A", "orcid_id": ""}]',
            "status": "draft",
        }
        form = DatasetInfoForm(data=form_data, user=self.user)
        # With MIN_AUTHOR_NAME_LENGTH = 0, this should pass
        # If the constant is changed to > 0, this test should fail
        assert form.is_valid()
