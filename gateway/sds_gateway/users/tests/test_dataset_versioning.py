"""Tests for dataset versioning (create new version from existing dataset)."""

import uuid

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from rest_framework import status

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import PermissionLevel
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.tests.factories import FileFactory
from sds_gateway.users.models import User
from sds_gateway.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db
FIRST_VERSION = 1
SECOND_VERSION = 2


def _create_dataset_with_files_and_captures(
    owner: User,
    version: int = FIRST_VERSION,
    **kwargs,
) -> Dataset:
    """Create a dataset with linked files and captures."""
    dataset = Dataset.objects.create(
        name=kwargs.get("name", "Test Dataset"),
        owner=owner,
        version=version,
        description=kwargs.get("description", "Description"),
        abstract=kwargs.get("abstract", "Abstract"),
        status=DatasetStatus.DRAFT.value,
        **{
            k: v
            for k, v in kwargs.items()
            if k not in ("name", "description", "abstract")
        },
    )
    file = FileFactory(owner=owner)
    capture = Capture.objects.create(
        owner=owner,
        capture_type=CaptureType.DigitalRF.value,
        name="Test capture",
    )
    dataset.files.add(file)
    dataset.captures.add(capture)
    return dataset


def _post_versioning(
    client: Client,
    dataset_uuid: uuid.UUID,
    *,
    copy_shared_users: bool = False,
) -> HttpResponse:
    url = reverse("users:dataset_versioning")
    data = {"dataset_uuid": str(dataset_uuid)}
    if copy_shared_users:
        data["copy_shared_users"] = "true"
    return client.post(url, data)


class TestDatasetVersioningNewVersionGreater:
    """Assert new version is greater than older one."""

    def test_new_version_is_incremented(self, client: Client) -> None:
        owner = UserFactory(is_approved=True)
        dataset = _create_dataset_with_files_and_captures(owner, version=1)
        client.force_login(owner)
        response = _post_versioning(client, dataset.uuid)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["version"] == SECOND_VERSION
        new_dataset = Dataset.objects.get(previous_version=dataset)
        assert new_dataset.version == SECOND_VERSION
        assert new_dataset.version > dataset.version


class TestDatasetVersioningMetadataCopied:
    """Assert metadata fields are copied correctly."""

    def test_metadata_copied_to_new_version(self, client: Client) -> None:
        owner = UserFactory(is_approved=True)
        dataset = _create_dataset_with_files_and_captures(
            owner,
            name="Original Name",
            description="Original description",
            abstract="Original abstract",
            doi="10.1234/test",
            license="MIT",
            website="https://example.com",
            provenance={"source": "test"},
            citation={"title": "Test"},
        )
        client.force_login(owner)
        response = _post_versioning(client, dataset.uuid)
        assert response.status_code == status.HTTP_200_OK
        new_dataset = Dataset.objects.get(previous_version=dataset)
        assert new_dataset.name == dataset.name
        assert new_dataset.description == dataset.description
        assert new_dataset.abstract == dataset.abstract
        assert new_dataset.doi == dataset.doi
        assert new_dataset.license == dataset.license
        assert new_dataset.website == dataset.website
        assert new_dataset.provenance == dataset.provenance
        assert new_dataset.citation == dataset.citation


class TestDatasetVersioningFilesAndCaptures:
    """Assert references to files and captures are the same."""

    def test_files_and_captures_same_as_original(self, client: Client) -> None:
        owner = UserFactory(is_approved=True)
        dataset = _create_dataset_with_files_and_captures(owner)
        original_file_ids = set(dataset.files.values_list("pk", flat=True))
        original_capture_ids = set(dataset.captures.values_list("pk", flat=True))
        client.force_login(owner)
        response = _post_versioning(client, dataset.uuid)
        assert response.status_code == status.HTTP_200_OK
        new_dataset = Dataset.objects.get(previous_version=dataset)
        assert set(new_dataset.files.values_list("pk", flat=True)) == original_file_ids
        assert (
            set(new_dataset.captures.values_list("pk", flat=True))
            == original_capture_ids
        )


class TestDatasetVersioningNonOwnerForbidden:
    """Assert non-owners cannot create derived versions."""

    def test_viewer_cannot_advance_version(self, client: Client) -> None:
        owner = UserFactory(is_approved=True)
        other = UserFactory(is_approved=True)
        dataset = _create_dataset_with_files_and_captures(owner)
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=other,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            permission_level=PermissionLevel.VIEWER,
        )
        client.force_login(other)
        response = _post_versioning(client, dataset.uuid)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert (
            "permission" in data["error"].lower() or "advance" in data["error"].lower()
        )
        assert not Dataset.objects.filter(previous_version=dataset).exists()

    def test_contributor_cannot_advance_version(self, client: Client) -> None:
        owner = UserFactory(is_approved=True)
        other = UserFactory(is_approved=True)
        dataset = _create_dataset_with_files_and_captures(owner)
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=other,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            permission_level=PermissionLevel.CONTRIBUTOR,
        )
        client.force_login(other)
        response = _post_versioning(client, dataset.uuid)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not Dataset.objects.filter(previous_version=dataset).exists()

    def test_unshared_user_cannot_advance_version(self, client: Client) -> None:
        owner = UserFactory(is_approved=True)
        other = UserFactory(is_approved=True)
        dataset = _create_dataset_with_files_and_captures(owner)
        client.force_login(other)
        response = _post_versioning(client, dataset.uuid)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert not Dataset.objects.filter(previous_version=dataset).exists()


class TestDatasetVersioningPreviousAndNext:
    """Assert previous_version and next_version are as expected."""

    def test_previous_version_and_next_version_linked(self, client: Client) -> None:
        owner = UserFactory(is_approved=True)
        dataset = _create_dataset_with_files_and_captures(owner, version=FIRST_VERSION)
        client.force_login(owner)
        response = _post_versioning(client, dataset.uuid)
        assert response.status_code == status.HTTP_200_OK
        new_dataset = Dataset.objects.get(previous_version=dataset)
        assert new_dataset.previous_version_id == dataset.pk
        assert dataset.next_version.filter(pk=new_dataset.pk).exists()
        assert dataset.next_version.get().version == SECOND_VERSION


class TestDatasetVersioningNotCarriedOver:
    """Assert timestamps, is_public, and shared users don't carry over by default."""

    def test_timestamps_do_not_carry_over(self, client: Client) -> None:
        owner = UserFactory(is_approved=True)
        dataset = _create_dataset_with_files_and_captures(owner)
        orig_created = dataset.created_at
        orig_updated = dataset.updated_at
        client.force_login(owner)
        response = _post_versioning(client, dataset.uuid)
        assert response.status_code == status.HTTP_200_OK
        new_dataset = Dataset.objects.get(previous_version=dataset)
        assert new_dataset.created_at >= orig_created
        assert new_dataset.updated_at >= orig_updated
        assert new_dataset.uuid != dataset.uuid

    def test_is_public_reset_to_false(self, client: Client) -> None:
        owner = UserFactory(is_approved=True)
        dataset = _create_dataset_with_files_and_captures(owner)
        dataset.is_public = True
        dataset.save(update_fields=["is_public"])
        client.force_login(owner)
        response = _post_versioning(client, dataset.uuid)
        assert response.status_code == status.HTTP_200_OK
        new_dataset = Dataset.objects.get(previous_version=dataset)
        assert new_dataset.is_public is False

    def test_shared_users_do_not_carry_over_when_not_requested(
        self, client: Client
    ) -> None:
        owner = UserFactory(is_approved=True)
        shared_user = UserFactory(is_approved=True)
        dataset = _create_dataset_with_files_and_captures(owner)
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=shared_user,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            permission_level=PermissionLevel.VIEWER,
        )
        client.force_login(owner)
        response = _post_versioning(client, dataset.uuid, copy_shared_users=False)
        assert response.status_code == status.HTTP_200_OK
        new_dataset = Dataset.objects.get(previous_version=dataset)
        new_perms = UserSharePermission.objects.filter(
            item_type=ItemType.DATASET,
            item_uuid=new_dataset.uuid,
        )
        assert not new_perms.exists()
