"""Tests for dataset status functionality."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.users.forms import DatasetInfoForm

User = get_user_model()


class TestDatasetStatus(TestCase):
    """Test dataset status functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",  # noqa: S106
            name="Test User",
            is_approved=True,
        )

    def test_dataset_status_choices(self):
        """Test that dataset status choices are correct."""
        choices = Dataset.STATUS_CHOICES
        expected_choices = [
            (DatasetStatus.DRAFT, "Draft"),
            (DatasetStatus.FINAL, "Final"),
        ]
        assert choices == expected_choices

    def test_dataset_default_status(self):
        """Test that new datasets have draft status by default."""
        dataset = Dataset.objects.create(
            name="Test Dataset",
            description="A test dataset",
            authors=["Test Author"],
            owner=self.user,
        )
        assert dataset.status == DatasetStatus.DRAFT

    def test_dataset_status_form_field(self):
        """Test that the form includes the status field with correct choices."""
        form = DatasetInfoForm(user=self.user)

        # Check that status field exists
        assert "status" in form.fields

        # Check that it has the correct choices
        expected_choices = [
            ("draft", "Draft"),
            ("final", "Final"),
        ]
        assert form.fields["status"].choices == expected_choices

        # Check that default is draft
        assert form.fields["status"].initial == "draft"

    def test_dataset_status_form_validation(self):
        """Test that the form validates status field correctly."""
        form_data = {
            "name": "Test Dataset",
            "description": "A test dataset",
            "author": "Test Author",
            "status": "final",
        }
        form = DatasetInfoForm(data=form_data, user=self.user)
        assert form.is_valid()
        assert form.cleaned_data["status"] == "final"

    def test_dataset_status_display(self):
        """Test that dataset status display works correctly."""
        dataset = Dataset.objects.create(
            name="Test Dataset",
            description="A test dataset",
            authors=["Test Author"],
            status=DatasetStatus.FINAL,
            owner=self.user,
        )
        assert dataset.get_status_display() == "Final"

    def test_dataset_status_update(self):
        """Test that dataset status can be updated."""
        dataset = Dataset.objects.create(
            name="Test Dataset",
            description="A test dataset",
            authors=["Test Author"],
            status=DatasetStatus.DRAFT,
            owner=self.user,
        )

        # Update status
        dataset.status = DatasetStatus.FINAL
        dataset.save()

        # Refresh from database
        dataset.refresh_from_db()
        assert dataset.status == DatasetStatus.FINAL
