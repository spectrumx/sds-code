"""Test cases for the endpoints that handle file operations."""

import logging
import uuid
from pathlib import Path
from typing import cast

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from rest_framework_api_key.models import AbstractAPIKey

from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.serializers.file_serializers import FilePostSerializer
from sds_gateway.users.models import UserAPIKey

User = get_user_model()
logger = logging.getLogger(__name__)


class FileTestCases(APITestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.user = User.objects.create(
            email="testuser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,  # allows creating API keys
        )

        api_key, key = UserAPIKey.objects.create_key(
            name="test-key",
            user=self.user,
        )
        self.api_key = cast(AbstractAPIKey, api_key)
        self.key = cast(str, key)

        # create a test file object
        self.file_contents = SimpleUploadedFile(
            "testfile.txt",
            content=b"file_content",
            content_type="text/plain",
        )
        file_data = {
            "file": self.file_contents,
            "directory": "/absolute/path/to/files",
            "media_type": "text/plain",
            "owner": self.user.pk,
        }
        serializer = FilePostSerializer(
            data=file_data,
            context={"request_user": self.user},
        )
        serializer.is_valid(raise_exception=True)
        self.file = serializer.save()

        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key: {self.key}")
        self.list_url = reverse("api:files-list")
        self.detail_url = reverse("api:files-detail", args=[self.file.uuid])
        self.contents_check_url = reverse("api:check_contents_exist")
        self.download_url = reverse("api:files-download", args=[self.file.uuid])

    def tearDown(self) -> None:
        # Delete the test file if it exists
        test_file_path = Path("testfile.txt")
        if test_file_path.exists():
            test_file_path.unlink()

    def test_create_file(self) -> None:
        with Path("testfile.txt").open("w") as file:
            file.write("This is a test file.")

        with Path("testfile.txt").open("rb") as file:
            data = {
                "file": file,
                "directory": "/absolute/path/to/files",
                "media_type": "text/plain",
            }
            response = self.client.post(self.list_url, data, format="multipart")

        assert response.status_code == status.HTTP_201_CREATED

    def test_retrieve_file_200(self) -> None:
        response = self.client.get(self.detail_url)
        assert response.status_code == status.HTTP_200_OK

    def test_retrieve_file_404(self) -> None:
        random_uuid = uuid.uuid4()
        response = self.client.get(
            reverse("api:files-detail", args=[random_uuid.hex]),
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_not_owned_file_404(self) -> None:
        """A user should not see a file that they do not own."""
        user = User.objects.create(
            email="john-doe@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )
        _, key = UserAPIKey.objects.create_key(
            name="test-key",
            user=user,
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Api-Key: {key}")
        response = client.get(
            reverse("api:files-detail", args=[self.file.uuid]),
        )
        assert (
            response.status_code == status.HTTP_404_NOT_FOUND
        ), f"Expected 404, got {response.status_code}"

    def test_retrieve_owned_file_200(self) -> None:
        """A user should see a file that they own."""
        user = User.objects.create(
            email="john-doe@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )
        _, key = UserAPIKey.objects.create_key(
            name="test-key",
            user=user,
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Api-Key: {key}")
        _file_created = File.objects.create(
            file=self.file_contents,
            directory=self.file.directory,
            media_type=self.file.media_type,
            size=self.file.size,
            owner=user,
        )
        response = client.get(
            reverse("api:files-detail", args=[_file_created.uuid]),
        )
        assert (
            response.status_code == status.HTTP_200_OK
        ), f"Expected 200, got {response.status_code}"

    def test_retrieve_latest_file_not_owned_404(self) -> None:
        """A user should not see the latest file that they do not own."""
        user = User.objects.create(
            email="john-doe@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )
        _, key = UserAPIKey.objects.create_key(
            name="test-key",
            user=user,
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Api-Key: {key}")
        response = client.get(
            self.list_url,
            data={"path": self.file.directory},
        )
        assert (
            response.status_code == status.HTTP_404_NOT_FOUND
        ), f"Expected 404, got {response.status_code}"

    def test_retrieve_latest_file_owned_200(self) -> None:
        """A user should see the latest file that they own."""
        user = User.objects.create(
            email="john-doe@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )
        _, key = UserAPIKey.objects.create_key(
            name="test-key",
            user=user,
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Api-Key: {key}")
        _file_created = File.objects.create(
            file=self.file_contents,
            directory=self.file.directory,
            media_type=self.file.media_type,
            size=self.file.size,
            owner=user,
        )
        response = client.get(
            self.list_url,
            data={"path": _file_created.directory},
        )
        assert (
            response.status_code == status.HTTP_200_OK
        ), f"Expected 200, got {response.status_code}"
        file_returned = response.data
        assert file_returned, "Expected a file to be returned"
        assert (
            file_returned.get("owner").get("email") == user.email
        ), f"Expected {user.email}, got {file_returned.get('owner').get('email')}"

    def test_update_file(self) -> None:
        data = {
            "name": "file_update.txt",
            "directory": f"/files/{self.user.email}/test_directory_2",
            "media_type": "text/plain",
        }
        response = self.client.put(
            self.detail_url,
            data,
            format="multipart",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == "file_update.txt"
        assert "test_directory_2" in response.data["directory"]

    def test_delete_file(self) -> None:
        response = self.client.delete(
            self.detail_url,
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_file_contents_check(self) -> None:
        metadata = {
            "directory": self.file.directory,
            "name": self.file.name,
            "sum_blake3": File().calculate_checksum(self.file_contents),
        }
        response = self.client.post(
            self.contents_check_url,
            metadata,
            format="multipart",
        )
        assert response.status_code == status.HTTP_200_OK
        assert "file_contents_exist_for_user" in response.data
        assert "file_exists_in_tree" in response.data
        assert "user_mutable_attributes_differ" in response.data

    def test_download_file(self):
        response = self.client.get(self.download_url)
        assert response.status_code == status.HTTP_200_OK
        assert (
            response["Content-Disposition"]
            == f'attachment; filename="{self.file.name}"'
        )
        assert response["Content-Type"] == self.file.media_type
        assert response.content == self.file.file.read()
