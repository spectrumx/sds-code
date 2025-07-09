"""
Tests for error email functionality in the users app.
"""

from django.core import mail
from django.test import TestCase
from django.test import override_settings

from sds_gateway.users.tasks import send_dataset_error_email


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class TestErrorEmails(TestCase):
    """Test error email sending functionality."""

    def test_send_dataset_error_email_success(self):
        """Test successful error email sending."""
        # Clear any existing emails
        mail.outbox.clear()

        # Test data
        user_email = "test@example.com"
        dataset_name = "Test Dataset"
        error_message = "No files found in dataset"

        # Send error email
        result = send_dataset_error_email.delay(user_email, dataset_name, error_message)
        expected_result = f"Error email sent to {user_email}"
        assert result.get() == expected_result, (
            f"Expected '{expected_result}', got '{result.get()}'"
        )

        # Verify email was sent
        assert len(mail.outbox) == 1, f"Expected 1 email, got {len(mail.outbox)}"
        email = mail.outbox[0]
        expected_subject = f"Dataset download failed: {dataset_name}"
        assert email.subject == expected_subject, (
            f"Expected subject '{expected_subject}', got '{email.subject}'"
        )
        assert email.to == [user_email], f"Expected to [{user_email}], got {email.to}"

        # Check email content
        expected_body_content = "No files found in dataset"
        assert expected_body_content in email.body, (
            f"Expected email body to contain '{expected_body_content}', "
            f"got '{email.body}'"
        )

        # Check HTML content
        assert len(email.alternatives) > 0, "Expected HTML alternative in email"
        assert email.alternatives[0][1] == "text/html", (
            "Expected text/html content type"
        )

    def test_send_dataset_error_email_failure(self):
        """Test error email sending when it fails."""
        # Test with invalid email address (should not crash)
        result = send_dataset_error_email.delay(
            "invalid-email", "Test Dataset", "Test error"
        )
        # Task should complete without raising an exception
        assert result.get() is not None, "Task result should not be None"
