import base64
import json
import uuid
from pathlib import Path

import numpy as np
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from rest_framework.test import APITestCase

from sds_gateway.api_methods.helpers.index_handling import create_index
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.serializers.file_serializers import FilePostSerializer
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.api_methods.views.capture_endpoints import CaptureViewSet
from sds_gateway.users.models import User


class OpenSearchHealthCheckTest(APITestCase):
    def setUp(self):
        self.client = get_opensearch_client()

    def test_opensearch_health_check(self):
        assert self.client.ping()


class OpenSearchIndexResetTest(APITestCase):
    def setUp(self):
        self.client = get_opensearch_client()
        self.test_index_prefix = "test-captures-"  # Add test prefix

        # Create test user
        self.user = User.objects.create(email="testuser@example.com")

        # Create test scan group
        self.scan_group = str(uuid.uuid4())
        self.top_level_dir = f"/files/{self.user.email}/{self.scan_group}"

        # Create a simple array of 10 float32 values
        test_data = np.array(
            [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0], dtype=np.float32
        )
        # Convert to bytes and base64 encode
        data_bytes = test_data.tobytes()
        data_base64 = base64.b64encode(data_bytes).decode("utf-8")

        # Create RH metadata JSON with simple test data
        self.json_file = {
            "altitude": 2.0,
            "center_frequency": 2000000000.0,
            "custom_fields": {
                "requested": {
                    "fmax": 2010000000,
                    "fmin": 1990000000,
                    "gain": 1,
                    "samples": 1024,
                    "span": 20000000,
                }
            },
            "data": data_base64,
            "gain": 1.0,
            "hardware_board_id": "025",
            "hardware_version": "3.4",
            "latitude": 41.699584,
            "longitude": -86.237237,
            "mac_address": "f4e11ea46780",
            "metadata": {
                "archive_result": True,
                "data_type": "periodogram",
                "fmax": 2012000000.0,
                "fmin": 1988000000.0,
                "gps_lock": False,
                "nfft": 1024,
                "scan_time": 0.07766938209533691,
            },
            "sample_rate": 24000000,
            "scan_group": self.scan_group,
            "short_name": "WI-Lab V3.4-025 #6",
            "software_version": "v0.10b30",
            "timestamp": "2025-01-10T15:48:07.100486Z",
            "type": "float32",
            "version": "v0",
        }

        # Create File object in MinIO/DB
        json_content = json.dumps(self.json_file).encode("utf-8")
        self.uploaded_file = SimpleUploadedFile(
            "test.rh.json", json_content, content_type="application/json"
        )

        file_data = {
            "directory": f"/{self.scan_group}",
            "file": self.uploaded_file,
            "media_type": "application/json",
            "name": "test.rh.json",
            "owner": self.user.pk,
        }
        serializer = FilePostSerializer(
            data=file_data,
            context={"request_user": self.user},
        )
        serializer.is_valid(raise_exception=True)
        self.file = serializer.save()

        # Create test capture with test index name
        self.capture = Capture.objects.create(
            owner=self.user,
            scan_group=self.scan_group,
            capture_type=CaptureType.RadioHound,
            index_name=f"{self.test_index_prefix}{CaptureType.RadioHound}",
            top_level_dir=self.top_level_dir,
        )

        self.initialize_opensearch_test_index()

        # Link file to capture
        self.file.capture = self.capture
        self.file.save()

        # Index the capture metadata
        capture_viewset = CaptureViewSet()
        capture_viewset.ingest_capture(
            capture=self.capture,
            drf_channel=None,
            rh_scan_group=self.scan_group,
            requester=self.user,
            top_level_dir=Path(self.top_level_dir),
            connect_files=False,
        )

        # Refresh index to make new documents searchable
        self.client.indices.refresh(
            index=f"{self.test_index_prefix}{self.capture.capture_type}"
        )

    def initialize_opensearch_test_index(self):
        # Create the index
        create_index(
            self.client,
            f"{self.test_index_prefix}{self.capture.capture_type}",
            self.capture.capture_type,
        )

    def test_opensearch_index_reset(self):
        # Get initial index name
        index_name = f"{self.test_index_prefix}{self.capture.capture_type}"

        # Verify initial document exists
        initial_response = self.client.search(
            index=index_name, body={"query": {"match": {"_id": str(self.capture.uuid)}}}
        )
        assert initial_response["hits"]["total"]["value"] == 1

        # Run reset_indices command
        call_command("reset_indices")

        # Allow time for indexing
        self.client.indices.refresh(index=index_name)

        # Verify document was reindexed
        after_response = self.client.search(
            index=index_name, body={"query": {"match": {"_id": str(self.capture.uuid)}}}
        )
        assert after_response["hits"]["total"]["value"] == 1

        # Verify metadata was preserved
        doc = after_response["hits"]["hits"][0]["_source"]
        assert (
            doc["capture_props"]["center_frequency"]
            == self.json_file["center_frequency"]
        )
        assert doc["capture_props"]["sample_rate"] == self.json_file["sample_rate"]

    def tearDown(self):
        """Clean up test data."""
        # Delete the entire test index
        self.client.indices.delete(index=f"{self.test_index_prefix}*")

        # Clean up the test capture and file
        self.capture.delete()
        self.file.delete()

        # Clean up the test user
        self.user.delete()
