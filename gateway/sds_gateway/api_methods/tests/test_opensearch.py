import base64
import json
import uuid
from pathlib import Path
from unittest import mock

import numpy as np
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from rest_framework.test import APITestCase

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
        self.test_index_prefix = "captures-test-"

        # Keep the original (old) mapping structure to test migration
        self.original_index_mapping = {
            "properties": {
                "channel": {"type": "keyword"},
                "scan_group": {"type": "keyword"},
                "capture_type": {"type": "keyword"},
                "created_at": {"type": "date"},
                "capture_props": {
                    "type": "nested",
                    "properties": {
                        "metadata": {
                            "type": "nested",
                            "properties": {
                                "archive_result": {"type": "boolean"},
                                "data_type": {"type": "keyword"},
                                "fmax": {"type": "float"},  # Old type: float
                                "fmin": {"type": "float"},  # Old type: float
                                "gps_lock": {"type": "boolean"},
                                "nfft": {"type": "integer"},
                                "scan_time": {"type": "float"},
                            },
                        },
                        "sample_rate": {"type": "integer"},  # Old type: integer
                        "center_frequency": {"type": "float"},  # Old type: float
                        "latitude": {"type": "float"},
                        "longitude": {"type": "float"},
                        "altitude": {"type": "float"},
                        "mac_address": {"type": "keyword"},
                        "short_name": {"type": "text"},
                    },
                },
                # Intentionally omitting search_props to test migration
            },
        }

        # Create test user
        self.user = User.objects.create(email="testuser@example.com")

        # Create test scan group
        self.scan_group = str(uuid.uuid4())
        self.top_level_dir = f"/files/{self.user.email}/{self.scan_group}"

        # Setup test data and create initial capture
        self._setup_test_data()
        self.capture = self._create_test_capture()
        self._initialize_test_index()
        self._index_test_capture()

    def _setup_test_data(self):
        """Setup test data for RH capture."""
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

    def _create_test_capture(self):
        """Create and index a test capture."""
        return Capture.objects.create(
            owner=self.user,
            scan_group=self.scan_group,
            capture_type=CaptureType.RadioHound,
            index_name=f"{self.test_index_prefix}{CaptureType.RadioHound}",
            top_level_dir=self.top_level_dir,
        )

    def _initialize_test_index(self):
        """Initialize test index with mapping."""

        # initialize test index with old mapping
        # incompatible with regular index mapping update
        # e.g. int -> long, float -> double
        original_index_config = {
            "mappings": self.original_index_mapping,
            "settings": {
                "index": {
                    "number_of_shards": 1,
                    "number_of_replicas": 1,
                },
            },
        }
        self.client.indices.create(
            index=self.capture.index_name,
            body=original_index_config,
        )

    def _index_test_capture(self):
        """Index test capture metadata."""
        capture_viewset = CaptureViewSet()
        capture_viewset.ingest_capture(
            capture=self.capture,
            drf_channel=None,
            rh_scan_group=self.scan_group,
            requester=self.user,
            top_level_dir=Path(self.top_level_dir),
        )

        # Refresh index
        self.client.indices.refresh(
            index=f"{self.test_index_prefix}{self.capture.capture_type}"
        )

    def test_successful_reindex(self):
        """Test successful reindex with matching document counts."""
        index_name = f"{self.test_index_prefix}{self.capture.capture_type}"

        # Get initial document
        initial_response = self.client.search(
            index=index_name, body={"query": {"match": {"_id": str(self.capture.uuid)}}}
        )
        assert initial_response["hits"]["total"]["value"] == 1

        # Mock user inputs and the mapping function
        with (
            mock.patch("builtins.input", return_value="y"),
        ):
            # Run replace_index command
            call_command(
                "replace_index",
                index_name=index_name,
                capture_type=self.capture.capture_type,
            )

        # Verify reindex
        self.client.indices.refresh(index=index_name)
        after_response = self.client.search(
            index=index_name, body={"query": {"match": {"_id": str(self.capture.uuid)}}}
        )
        assert after_response["hits"]["total"]["value"] == 1

        # Verify metadata preserved
        doc = after_response["hits"]["hits"][0]["_source"]
        assert (
            doc["capture_props"]["center_frequency"]
            == self.json_file["center_frequency"]
        )
        assert doc["capture_props"]["sample_rate"] == self.json_file["sample_rate"]

    def test_fail_state_reset_to_original(self):
        """Test that the reindex fails and is reset to original state."""
        index_name = f"{self.test_index_prefix}{self.capture.capture_type}"

        # Get initial state - should have 1 document (our test capture)
        initial_count = self.client.count(index=index_name)["count"]
        assert initial_count == 1

        # Get initial mapping to verify reset later
        initial_mapping = self.client.indices.get_mapping(
            index=index_name,
        )[index_name]["mappings"]

        # Mock user inputs and the mapping function
        with (
            mock.patch("builtins.input", return_value="y"),
            mock.patch(
                "sds_gateway.api_methods.utils.metadata_schemas.get_mapping_by_capture_type"
            ) as mock_mapping,
        ):
            # Return an invalid mapping that will cause reindex to fail
            mock_mapping.return_value = {
                "properties": {
                    "capture_props": {
                        "type": "keyword"  # This conflicts with nested type
                    }
                }
            }

            # Run replace_index command
            call_command(
                "replace_index",
                index_name=index_name,
                capture_type=self.capture.capture_type,
            )

        # Verify final state
        self.client.indices.refresh(index=index_name)
        final_count = self.client.count(index=index_name)["count"]
        assert final_count == 1  # Original document count preserved

        # Verify mapping was reset to original
        final_mapping = self.client.indices.get_mapping(
            index=index_name,
        )[index_name]["mappings"]
        assert final_mapping == initial_mapping

        # Verify no backup indices remain
        backup_indices = self.client.indices.get(index=f"{index_name}-backup-*")
        assert len(backup_indices) == 0

    def test_duplicate_capture_deletion(self):
        """Test that duplicate captures are deleted."""
        index_name = f"{self.test_index_prefix}{self.capture.capture_type}"

        # Get initial document
        initial_response = self.client.search(
            index=index_name, body={"query": {"match": {"_id": str(self.capture.uuid)}}}
        )
        assert initial_response["hits"]["total"]["value"] == 1

        # Create duplicate capture
        self._create_test_capture()
        self._index_test_capture()

        # Verify duplicate capture was created
        duplicate_capture = (
            Capture.objects.filter(
                scan_group=self.scan_group,
                capture_type=self.capture.capture_type,
            )
            .exclude(uuid=self.capture.uuid)
            .first()
        )
        assert duplicate_capture is not None

        # Run replace_index command with test prefix
        call_command(
            "replace_index",
            index_name=index_name,
            capture_type=self.capture.capture_type,
        )

        # Verify duplicate captures are deleted
        final_response = self.client.search(
            index=index_name, body={"query": {"match": {"_id": str(self.capture.uuid)}}}
        )
        assert final_response["hits"]["total"]["value"] == 1

    def tearDown(self):
        """Clean up test data."""
        # Delete test indices
        self.client.indices.delete(index=f"{self.test_index_prefix}*", ignore=[404])

        # Clean up test objects in correct order
        self.capture.delete()

        # Then delete the file
        self.file.delete()

        # Finally delete the user
        self.user.delete()
