"""Test cases for the endpoints that handle file operations."""

import time
import uuid
from pathlib import Path
from typing import Any
from typing import cast

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.test import APITestCase
from rest_framework_api_key.models import AbstractAPIKey

from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.serializers.file_serializers import FilePostSerializer
from sds_gateway.users.models import UserAPIKey

User = get_user_model()


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
        self.file_name = "testfile.txt"
        self.test_file_path = Path(self.file_name)
        self.file_contents = SimpleUploadedFile(
            self.file_name,
            content=b"file_content",
            content_type="text/plain",
        )
        self.sds_path = "/absolute/path/to/files"
        self.file_data = {
            "directory": self.sds_path,
            "file": self.file_contents,
            "media_type": "text/plain",
            "name": self.file_name,
            "owner": self.user.pk,
        }
        serializer = FilePostSerializer(
            data=self.file_data,
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
        """Clean up test files."""
        self.test_file_path.unlink(missing_ok=True)

    def test_create_file(self) -> None:
        with self.test_file_path.open("w") as fp:
            fp.write("This is a test file.")

        with self.test_file_path.open("rb") as fp:
            data = {
                "file": fp,
                "directory": f"/files/{self.user.email}/",
                "media_type": "text/plain",
            }
            response = self.client.post(self.list_url, data=data, format="multipart")

        assert response.status_code == status.HTTP_201_CREATED

    def test_retrieve_file_200(self) -> None:
        """Retrieving the file details should return a 200."""
        response = self.client.get(self.detail_url)
        assert response.status_code == status.HTTP_200_OK

    def test_retrieve_file_404(self) -> None:
        """Retrieving a missing file should return a 404."""
        random_uuid = uuid.uuid4()
        response = self.client.get(
            reverse("api:files-detail", args=[random_uuid.hex]),
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_not_owned_file_404(self) -> None:
        """A user should not see a file that they do not own."""
        user_mallory = User.objects.create(
            email="mallory@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )
        _, key = UserAPIKey.objects.create_key(
            name="test-key",
            user=user_mallory,
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Api-Key: {key}")
        response = client.get(
            reverse("api:files-detail", args=[self.file.uuid]),
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND, (
            f"Expected 404, got {response.status_code}"
        )

    def test_retrieve_owned_file_200(self) -> None:
        """A user should see a file that they own."""
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Api-Key: {self.key}")
        _file_created = self.file
        response = client.get(
            reverse("api:files-detail", args=[_file_created.uuid]),
        )
        assert response.status_code == status.HTTP_200_OK, (
            f"Expected 200, got {response.status_code}"
        )

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
        results = response.data.get("results")
        assert len(results) == 0, f"Expected no files to be returned, got {results}"

    def test_retrieve_latest_file_owned_200(self) -> None:
        """On multiple dir + name matches, the most recent should be returned."""
        # create a new file with the same directory and name as the original one
        new_contents_bytes = b"new file content"
        new_contents = SimpleUploadedFile(
            self.file_name,
            content=new_contents_bytes,
            content_type="text/plain",
        )
        new_file_data = {
            "directory": self.sds_path,
            "file": new_contents,
            "media_type": self.file.media_type,
            "name": self.file_name,
            "owner": self.user.pk,
        }
        serializer = FilePostSerializer(
            data=new_file_data,
            context={"request_user": self.user},
        )
        serializer.is_valid(raise_exception=True)
        new_file = serializer.save()

        time.sleep(1)  # ensure the new file is created after the original one

        saved_contents = new_file.file.read()
        assert len(saved_contents) > 0, "Expected content in the new file"

        # make sure new file with conflicting path + name is correctly created
        assert new_file.directory == self.file.directory, (
            "Expected the same directory: "
            f"{new_file.directory} != {self.file.directory}"
        )
        assert new_file.name == self.file.name, (
            f"Expected the same name: {new_file.name} != {self.file.name}"
        )
        assert new_file.created_at > self.file.created_at, (
            "Expected a newer file: {new_file.created_at} <= {self.file.created_at}"
        )
        assert new_file.owner == self.user, (
            f"Unexpected owner: {new_file.owner} != {self.user}"
        )
        assert saved_contents == new_contents_bytes, (
            "Expected the content of the new file: "
            f"{saved_contents} != {new_contents_bytes}"
        )
        assert new_file.uuid != self.file.uuid, (
            f"Expected a different file instance: {new_file.uuid} == {self.file.uuid}"
        )

        # get the latest file at this location
        file_request = f"{self.sds_path}/{new_file.name}"
        response = self.client.get(
            self.list_url,
            data={"path": file_request},
        )

        assert response.status_code == status.HTTP_200_OK, (
            f"Expected 200, got {response.status_code}"
        )
        response = response.data
        assert "results" in response, (
            f"Expected a paginated response with 'results', got: {response}"
        )
        files_returned: list[dict[str, Any]] = response.get("results")
        assert isinstance(
            files_returned,
            list,
        ), f"Expected a list of files as result, got: {type(files_returned)}"
        assert len(files_returned) == 1, (
            f"Expected exactly one file to be returned. {files_returned}"
        )

        old_file_uuid = str(self.file.uuid)
        retrieved_uuid = str(files_returned[0].get("uuid"))
        new_file_uuid = str(new_file.uuid)
        assert retrieved_uuid == new_file_uuid != old_file_uuid, (
            f"{retrieved_uuid=} == {new_file_uuid=} != {old_file_uuid=}"
        )

    def test_update_file(self) -> None:
        """Updates the file name and directory."""
        updated_file_name = "file_update.txt"
        data = {
            "name": updated_file_name,
            "directory": "/test_directory_2",
            "media_type": "text/plain",
        }
        response = self.client.put(
            self.detail_url,  # the file UUID to update is in the URL
            data=data,
            format="multipart",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["name"] == updated_file_name, response.data
        assert "test_directory_2" in response.data["directory"], response.data

    def test_delete_file(self) -> None:
        """Make sure the file is deleted."""

        # Create a new file to be deleted
        ephemeral_file_data = {
            "directory": self.sds_path,
            "file": SimpleUploadedFile(
                "file_to_delete.txt",
                content=b"delete me",
                content_type="text/plain",
            ),
            "media_type": "text/plain",
            "name": "file_to_delete.txt",
            "owner": self.user.pk,
        }
        serializer = FilePostSerializer(
            data=ephemeral_file_data,
            context={"request_user": self.user},
        )
        serializer.is_valid(raise_exception=True)
        ephemeral_file = serializer.save()

        # Update the detail URL to point to the new file
        try:
            self.detail_url = reverse("api:files-detail", args=[ephemeral_file.uuid])
            response = self.client.delete(
                self.detail_url,
            )
            assert response.status_code == status.HTTP_204_NO_CONTENT
        finally:
            ephemeral_file.delete()

    def test_file_contents_check(self) -> None:
        metadata = {
            "directory": self.file.directory,
            "name": self.file.name,
            "sum_blake3": File().calculate_checksum(self.file_contents),
        }
        response = self.client.post(
            self.contents_check_url,
            data=metadata,
            format="multipart",
        )
        assert response.status_code == status.HTTP_200_OK
        assert "file_contents_exist_for_user" in response.data
        assert "file_exists_in_tree" in response.data
        assert "user_mutable_attributes_differ" in response.data

    def test_download_file(self) -> None:
        """When downloading a file, the contents should match the uploaded file."""
        response = self.client.get(self.download_url)
        assert response.status_code == status.HTTP_200_OK
        assert (
            response["Content-Disposition"]
            == f'attachment; filename="{self.file.name}"'
        )
        assert response["Content-Type"] == self.file.media_type
        assert response.content == self.file.file.read()
