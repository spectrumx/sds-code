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
EXPECTED_FILES_COUNT = 3


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class TestCeleryTasks(TestCase):
    """Test cases for Celery tasks."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",  # noqa: S106
            is_approved=True,
        )

        self.base_dir = "/files/test@example.com/"
        self.rel_path_capture = "captures/test_capture/"
        self.rel_path_artifacts = "artifacts/"
        self.top_level_dir = f"{self.base_dir}{self.rel_path_capture}"

        # Create a test dataset
        self.dataset = Dataset.objects.create(
            name="Test Dataset",
            description="A test dataset for testing",
            owner=self.user,
        )

        # Create a test capture
        self.capture = Capture.objects.create(
            channel="test_channel",
            capture_type="drf",
            top_level_dir=self.top_level_dir,
            owner=self.user,
        )

        # Link capture to dataset
        self.dataset.captures.add(self.capture)

        # Create test files
        self.file1 = File.objects.create(
            name="test_file1.txt",
            size=1024,
            directory=self.top_level_dir,
            owner=self.user,
            capture=self.capture,
        )

        self.file2 = File.objects.create(
            name="test_file2.txt",
            size=2048,
            directory=f"{self.top_level_dir}subdir/",
            owner=self.user,
            capture=self.capture,
        )

        self.file3 = File.objects.create(
            name="test_file3.txt",
            size=3072,
            directory=f"{self.base_dir}{self.rel_path_artifacts}",
            owner=self.user,
        )

        # Add files directly to dataset
        self.dataset.files.add(self.file3)

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
            # Check that all three files are in the zip
            file_list = zip_file.namelist()
            expected_file1 = f"{self.rel_path_capture}test_file1.txt"
            expected_file2 = f"{self.rel_path_capture}subdir/test_file2.txt"
            expected_file3 = f"{self.rel_path_artifacts}test_file3.txt"
            assert expected_file1 in file_list, (
                f"Expected '{expected_file1}' in zip, got {file_list}"
            )
            assert expected_file2 in file_list, (
                f"Expected '{expected_file2}' in zip, got {file_list}"
            )
            assert expected_file3 in file_list, (
                f"Expected '{expected_file3}' in zip, got {file_list}"
            )

            # Check file contents
            expected_content = b"test file content"
            file1_content = zip_file.read(expected_file1)
            assert file1_content == expected_content, (
                f"Expected file content '{expected_content}', got '{file1_content}'"
            )
            file2_content = zip_file.read(expected_file2)
            assert file2_content == expected_content, (
                f"Expected file content '{expected_content}', got '{file2_content}'"
            )
            file3_content = zip_file.read(expected_file3)
            assert file3_content == expected_content, (
                f"Expected file content '{expected_content}', got '{file3_content}'"
            )

    @patch("sds_gateway.api_methods.tasks.download_file")
    def test_send_dataset_files_email_no_files(self, mock_download_file):
        """Test dataset email task when no files are found."""
        # Create a dataset with no files
        empty_dataset = Dataset.objects.create(
            name="Empty Dataset",
            description="A dataset with no files",
            owner=self.user,
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
    def test_send_dataset_files_email_download_failure(self, mock_download_file):
        """Test dataset email task when file download fails."""
        # Mock download_file to raise an exception
        mock_download_file.side_effect = OSError("Download failed")

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
