# Create your tests here.
# tests.py
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.test import APITestCase

from sds_gateway.api_methods.serializers.file_serializers import FilePostSerializer

User = get_user_model()


class FileTestCases(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create(
            email="testuser@example.com",
            password="testpassword",  # noqa: S106
        )
        # Create a test file object
        self.file_obj = SimpleUploadedFile(
            "testfile.txt",
            b"file_content",
            content_type="text/plain",
        )
        file_data = {
            "file": self.file_obj,
            "directory": "test_directory",
            "media_type": "text/plain",
        }
        serializer = FilePostSerializer(
            data=file_data,
            context={"request_user": self.user},
        )
        serializer.is_valid(raise_exception=True)
        self.file = serializer.save()

        self.client.force_authenticate(user=self.user)
        self.list_url = reverse("api:files-list")
        self.detail_url = reverse("api:files-detail", args=[self.file.uuid])

    def test_create_file(self):
        with Path("testfile.txt").open("w") as file:
            file.write("This is a test file.")

        with Path("testfile.txt").open("rb") as file:
            data = {
                "file": file,
                "directory": "test_directory",
                "media_type": "text/plain",
            }
            response = self.client.post(self.list_url, data, format="multipart")

        assert response.status_code == status.HTTP_201_CREATED

    def test_retrieve_file(self):
        response = self.client.get(reverse("api:files-detail", args=[self.file.uuid]))
        assert response.status_code == status.HTTP_200_OK

    def test_retrieve_latest_file(self):
        response = self.client.get(
            self.list_url,
            {"path": self.file.directory},
        )
        assert response.status_code == status.HTTP_200_OK

    def test_update_file(self):
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

    def test_delete_file(self):
        response = self.client.delete(
            self.detail_url,
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT
