import json
import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files import File as DjangoFile
from minio.error import MinioException
from rest_framework.test import APITestCase

from sds_gateway.api_methods.helpers.reconstruct_file_tree import reconstruct_tree
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.serializers.file_serializers import FilePostSerializer
from sds_gateway.api_methods.utils.minio_client import get_minio_client

User = get_user_model()


def try_get_bucket(client):
    try:
        return client.bucket_exists(settings.AWS_STORAGE_BUCKET_NAME)
    except (MinioException, ConnectionError) as e:
        return str(e)


class MinioHealthCheckTest(APITestCase):
    def setUp(self):
        self.client = get_minio_client()

    def test_minio_health_check(self):
        response = try_get_bucket(self.client)

        assert response is True


class ReconstructRHFileTreeTest(APITestCase):
    """Test reconstructing RadioHound file trees with scan groups."""

    def setUp(self):
        self.client = get_minio_client()
        self.scan_group = uuid.uuid4()

        # Create test user
        self.user = User.objects.create(
            email="testuser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )

        # Create test directory structure with user's email prefix
        self.top_level_dir = Path("/files/testuser@example.com/rh_test_dir/")
        self.rh_test_dir = "/rh_test_dir"

        # Create sample RH metadata files
        self.rh_data = {
            "altitude": 2.0,
            "center_frequency": 2000000000.0,
            "scan_group": str(self.scan_group),
            "metadata": {
                "data_type": "periodogram",
                "fmax": 2012000000,
                "fmin": 1988000000,
                "gps_lock": False,
            },
            "sample_rate": 24000000,
            "timestamp": "2025-01-10T15:48:07.100486Z",
        }

        # Create files with different scan groups
        self.matching_files = []
        self.non_matching_files = []

        # Create 3 files with matching scan group
        for i in range(3):
            file_name = f"test_data_{i}.rh.json"

            # Create temporary file with content and create File object
            with tempfile.NamedTemporaryFile(
                mode="w+b",
                delete=False,
                suffix=".rh.json",
            ) as tmp_file:
                # Write the JSON data
                data = self.rh_data.copy()
                data["file_number"] = i
                json_data = json.dumps(data).encode()
                tmp_file.write(json_data)
                tmp_file.flush()

                # Rewind file for Django
                tmp_file.seek(0)
                django_file = DjangoFile(tmp_file, name=file_name)

                # Create the File object
                serializer = FilePostSerializer(
                    data={
                        "file": django_file,
                        "name": file_name,
                        "directory": self.rh_test_dir,
                        "media_type": "application/json",
                        "permissions": "rw-r--r--",
                    },
                    context={"request_user": self.user},
                )
                if serializer.is_valid():
                    file = serializer.save()
                    self.matching_files.append(file)
                else:
                    msg = f"Invalid file data: {serializer.errors}"
                    raise ValueError(msg)

        # Create 2 files with different scan group
        other_scan_group = uuid.uuid4()
        for i in range(2):
            file_name = f"other_data_{i}.rh.json"

            # Create temporary file with content and create File object
            with tempfile.NamedTemporaryFile(
                mode="w+b",
                delete=False,
                suffix=".rh.json",
            ) as tmp_file:
                # Write the JSON data
                data = self.rh_data.copy()
                data["scan_group"] = str(other_scan_group)
                data["file_number"] = i
                json_data = json.dumps(data).encode()
                tmp_file.write(json_data)
                tmp_file.flush()

                # Rewind file for Django
                tmp_file.seek(0)
                django_file = DjangoFile(tmp_file, name=file_name)

                # Create the File object
                serializer = FilePostSerializer(
                    data={
                        "file": django_file,
                        "name": file_name,
                        "directory": self.rh_test_dir,
                        "media_type": "application/json",
                        "permissions": "rw-r--r--",
                    },
                    context={"request_user": self.user},
                )
                if serializer.is_valid():
                    file = serializer.save()
                    self.non_matching_files.append(file)
                else:
                    msg = f"Invalid file data: {serializer.errors}"
                    raise ValueError(msg)

    def tearDown(self):
        # Clean up files in MinIO and database
        for file in self.matching_files + self.non_matching_files:
            file.file.delete()  # Delete from MinIO
            file.delete()  # Delete from database

    def test_reconstruct_tree_with_scan_group(self):
        """Test reconstructing tree filters by scan group."""
        with tempfile.TemporaryDirectory() as temp_dir:
            reconstructed_root, files = reconstruct_tree(
                target_dir=Path(temp_dir),
                virtual_top_dir=self.top_level_dir,
                owner=self.user,
                drf_capture_type=CaptureType.RadioHound,
                rh_scan_group=self.scan_group,
            )

            # Should only return files matching scan group
            assert len(files) == len(self.matching_files)
            for file in files:
                assert file in self.matching_files
                assert file not in self.non_matching_files

            # Verify files were reconstructed
            for file in files:
                reconstructed_path = reconstructed_root / file.name
                assert reconstructed_path.exists()

                # Verify content
                with reconstructed_path.open() as f:
                    content = json.load(f)
                    assert content["scan_group"] == str(self.scan_group)
