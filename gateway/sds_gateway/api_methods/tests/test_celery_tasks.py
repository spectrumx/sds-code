"""
Tests for Celery tasks in the API methods app.
"""

import io
import zipfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.test import override_settings

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.tasks import send_dataset_files_email
from sds_gateway.api_methods.tasks import test_celery_task
from sds_gateway.api_methods.tasks import test_email_task

User = get_user_model()

# Test constants
EXPECTED_FILES_COUNT = 2


class TestCeleryTasks(TestCase):
    """Test cases for Celery tasks."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",  # noqa: S106
            is_approved=True,
        )

        # Create a test dataset
        self.dataset = Dataset.objects.create(
            name="Test Dataset",
            description="A test dataset for testing",
            created_by=self.user,
            is_public=True,
        )

        # Create a test capture
        self.capture = Capture.objects.create(
            name="Test Capture",
            description="A test capture",
            created_by=self.user,
            is_public=True,
        )

        # Link capture to dataset
        self.dataset.captures.add(self.capture)

        # Create test files
        self.file1 = File.objects.create(
            name="test_file1.txt",
            size=1024,
            directory="files/",
            capture=self.capture,
            minio_path="test/path/file1.txt",
        )

        self.file2 = File.objects.create(
            name="test_file2.txt",
            size=2048,
            directory="files/subdir/",
            capture=self.capture,
            minio_path="test/path/file2.txt",
        )

    def test_test_celery_task(self):
        """Test the basic Celery task functionality."""
        # Test with default message
        result = test_celery_task.delay()
        expected_result = "Hello from Celery! - Task completed successfully!"
        assert result.get() == expected_result, (
            f"Expected '{expected_result}', got '{result.get()}'"
        )

        # Test with custom message
        custom_message = "Custom message"
        result = test_celery_task.delay(custom_message)
        expected_result = f"{custom_message} - Task completed successfully!"
        assert result.get() == expected_result, (
            f"Expected '{expected_result}', got '{result.get()}'"
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_test_email_task(self):
        """Test the email sending task."""
        # Clear any existing emails
        mail.outbox.clear()

        # Test email sending
        result = test_email_task.delay("test@example.com")
        expected_result = "Test email sent to test@example.com"
        assert result.get() == expected_result, (
            f"Expected '{expected_result}', got '{result.get()}'"
        )

        # Verify email was sent
        assert len(mail.outbox) == 1, f"Expected 1 email, got {len(mail.outbox)}"
        email = mail.outbox[0]
        assert email.subject == "Test Email from Celery", (
            f"Expected subject 'Test Email from Celery', got '{email.subject}'"
        )
        assert email.to == ["test@example.com"], (
            f"Expected to ['test@example.com'], got {email.to}"
        )
        expected_body_content = "This is a test email sent from Celery"
        assert expected_body_content in email.body, (
            f"Expected email body to contain '{expected_body_content}', "
            f"got '{email.body}'"
        )

    @patch("sds_gateway.api_methods.tasks.download_file")
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_dataset_files_email_success(self, mock_download_file):
        """Test successful dataset files email sending."""
        # Mock the download_file function to return test content
        mock_download_file.return_value = b"test file content"

        # Clear any existing emails
        mail.outbox.clear()

        # Test the task
        result = send_dataset_files_email.delay(
            str(self.dataset.uuid), "test@example.com"
        )

        # Get the result
        task_result = result.get()

        # Verify task completed successfully
        assert task_result["status"] == "success", (
            f"Expected status 'success', got '{task_result['status']}'"
        )
        assert task_result["files_processed"] == EXPECTED_FILES_COUNT, (
            f"Expected {EXPECTED_FILES_COUNT} files processed, "
            f"got {task_result['files_processed']}"
        )
        assert "zip_filename" in task_result, (
            f"Expected 'zip_filename' in result, got {task_result.keys()}"
        )

        # Verify email was sent
        assert len(mail.outbox) == 1, f"Expected 1 email, got {len(mail.outbox)}"
        email = mail.outbox[0]
        expected_subject = f"Dataset Files: {self.dataset.name}"
        assert email.subject == expected_subject, (
            f"Expected subject '{expected_subject}', got '{email.subject}'"
        )
        assert email.to == ["test@example.com"], (
            f"Expected to ['test@example.com'], got {email.to}"
        )
        expected_attachment_name = "dataset_Test_Dataset"
        assert expected_attachment_name in email.attachments[0][0], (
            f"Expected attachment name to contain '{expected_attachment_name}', "
            f"got '{email.attachments[0][0]}'"
        )

        # Verify zip file was created with correct content
        zip_data = email.attachments[0][1]
        with zipfile.ZipFile(io.BytesIO(zip_data), "r") as zip_file:
            # Check that both files are in the zip
            file_list = zip_file.namelist()
            assert "test_file1.txt" in file_list, (
                f"Expected 'test_file1.txt' in zip, got {file_list}"
            )
            assert "subdir/test_file2.txt" in file_list, (
                f"Expected 'subdir/test_file2.txt' in zip, got {file_list}"
            )

            # Check file contents
            expected_content = b"test file content"
            file1_content = zip_file.read("test_file1.txt")
            assert file1_content == expected_content, (
                f"Expected file content '{expected_content}', got '{file1_content}'"
            )
            file2_content = zip_file.read("subdir/test_file2.txt")
            assert file2_content == expected_content, (
                f"Expected file content '{expected_content}', got '{file2_content}'"
            )

    @patch("sds_gateway.api_methods.tasks.download_file")
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_dataset_files_email_no_files(self, mock_download_file):
        """Test dataset email task when no files are found."""
        # Create a dataset with no files
        empty_dataset = Dataset.objects.create(
            name="Empty Dataset",
            description="A dataset with no files",
            created_by=self.user,
            is_public=True,
        )

        # Clear any existing emails
        mail.outbox.clear()

        # Test the task
        result = send_dataset_files_email.delay(
            str(empty_dataset.uuid), "test@example.com"
        )

        # Get the result
        task_result = result.get()

        # Verify task completed with warning
        assert task_result["status"] == "warning", (
            f"Expected status 'warning', got '{task_result['status']}'"
        )
        assert task_result["files_processed"] == 0, (
            f"Expected 0 files processed, got {task_result['files_processed']}"
        )
        expected_message = "No files found in the dataset"
        assert task_result["message"] == expected_message, (
            f"Expected message '{expected_message}', got '{task_result['message']}'"
        )

        # Verify no email was sent
        assert len(mail.outbox) == 0, f"Expected 0 emails, got {len(mail.outbox)}"

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_dataset_files_email_dataset_not_found(self):
        """Test dataset email task when dataset doesn't exist."""
        # Clear any existing emails
        mail.outbox.clear()

        # Test with non-existent dataset UUID
        result = send_dataset_files_email.delay(
            "00000000-0000-0000-0000-000000000000", "test@example.com"
        )

        # Get the result
        task_result = result.get()

        # Verify task failed
        assert task_result["status"] == "error", (
            f"Expected status 'error', got '{task_result['status']}'"
        )
        expected_message = "Dataset not found"
        assert task_result["message"] == expected_message, (
            f"Expected message '{expected_message}', got '{task_result['message']}'"
        )

        # Verify no email was sent
        assert len(mail.outbox) == 0, f"Expected 0 emails, got {len(mail.outbox)}"

    @patch("sds_gateway.api_methods.tasks.download_file")
    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_send_dataset_files_email_download_failure(self, mock_download_file):
        """Test dataset email task when file download fails."""
        # Mock download_file to raise an exception
        mock_download_file.side_effect = Exception("Download failed")

        # Clear any existing emails
        mail.outbox.clear()

        # Test the task
        result = send_dataset_files_email.delay(
            str(self.dataset.uuid), "test@example.com"
        )

        # Get the result
        task_result = result.get()

        # Verify task completed with error
        assert task_result["status"] == "error", (
            f"Expected status 'error', got '{task_result['status']}'"
        )
        assert task_result["files_processed"] == 0, (
            f"Expected 0 files processed, got {task_result['files_processed']}"
        )
        expected_message = "Failed to process any files"
        assert task_result["message"] == expected_message, (
            f"Expected message '{expected_message}', got '{task_result['message']}'"
        )

        # Verify no email was sent
        assert len(mail.outbox) == 0, f"Expected 0 emails, got {len(mail.outbox)}"

    def test_task_error_handling(self):
        """Test that tasks handle errors gracefully."""
        # Test with invalid email address (should not crash)
        result = test_email_task.delay("invalid-email")
        # Task should complete without raising an exception
        assert result.get() is not None, "Task result should not be None"
