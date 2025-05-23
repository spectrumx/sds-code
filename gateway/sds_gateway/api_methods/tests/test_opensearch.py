"""Tests for OpenSearch index reset and reindexing."""

import base64
import json
import uuid
from pathlib import Path
from typing import cast
from unittest import mock

import numpy as np
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from loguru import logger
from opensearchpy.exceptions import RequestError
from rest_framework.test import APITestCase

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.serializers.file_serializers import FilePostSerializer
from sds_gateway.api_methods.utils.metadata_schemas import get_mapping_by_capture_type
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.api_methods.views.capture_endpoints import CaptureViewSet
from sds_gateway.users.models import User


class OpenSearchHealthCheckTest(APITestCase):
    def setUp(self) -> None:
        self.client = get_opensearch_client()

    def test_opensearch_health_check(self) -> None:
        assert self.client.ping()


class OpenSearchRHIndexResetTest(APITestCase):
    def setUp(self) -> None:
        self.client = get_opensearch_client()
        self.test_index_prefix = "captures-test-"
        self.capture_type = CaptureType.RadioHound
        self.index_name = f"{self.test_index_prefix}{self.capture_type}"

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
        self.capture = self._create_test_capture(self.user, self.top_level_dir)
        self._initialize_test_index()
        self._index_test_capture(self.capture)

    def tearDown(self) -> None:
        """Clean up test data"""
        self.client.indices.delete(
            index=f"{self.test_index_prefix}*",
            ignore_unavailable=True,  # pyright: ignore[reportCallIssue]
        )

        # clean up test objects in correct order
        self.user.captures.all().delete()
        self.file.delete()
        self.user.delete()

    def _setup_test_data(self) -> None:
        """Setup test data for RH capture."""
        # Create a simple array of 10 float32 values
        test_data = np.array(
            [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
            dtype=np.float32,
        )
        # Convert to bytes and base64 encode
        data_bytes = test_data.tobytes()
        data_base64 = base64.b64encode(data_bytes).decode("utf-8")

        # Create RH metadata JSON with simple test data
        self.json_file = {
            "altitude": 2.0,
            "center_frequency": 2_000_000_000.0,
            "custom_fields": {
                "requested": {
                    "fmax": 2_010_000_000.0,
                    "fmin": 1_990_000_000.0,
                    "gain": 1,
                    "samples": 1024,
                    "span": 20_000_000,
                },
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
                "fmax": 2_012_000_000.0,
                "fmin": 1_988_000_000.0,
                "gps_lock": False,
                "nfft": 1024,
                "scan_time": 0.07766938209533691,
            },
            "sample_rate": 24_000_000,
            "scan_group": self.scan_group,
            "short_name": "WI-Lab V3.4-025 #6",
            "software_version": "v0.10b30",
            "timestamp": "2025-01-10T15:48:07.100486Z",
            "type": "float32",
            "version": "v0",
        }

        self.file = self._create_test_file(self.user)

    def _create_test_capture(self, owner: User, top_level_dir: str) -> Capture:
        """Create and index a test capture."""
        return Capture.objects.create(
            owner=owner,
            scan_group=self.scan_group,
            capture_type=self.capture_type,
            index_name=self.index_name,
            top_level_dir=top_level_dir,
        )

    def _create_test_file(self, owner: User) -> File:
        # Create File object in MinIO/DB
        json_content = json.dumps(self.json_file).encode("utf-8")
        self.uploaded_file = SimpleUploadedFile(
            "test.rh.json",
            json_content,
            content_type="application/json",
        )

        file_data = {
            "directory": f"/{self.scan_group}",
            "file": self.uploaded_file,
            "media_type": "application/json",
            "name": "test.rh.json",
            "owner": owner.pk,
        }
        serializer = FilePostSerializer(
            data=file_data,
            context={"request_user": owner},
        )
        serializer.is_valid(raise_exception=True)
        return serializer.save()

    def _initialize_test_index(self) -> None:
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

    def _index_test_capture(self, capture: Capture) -> None:
        """Index test capture metadata."""
        capture_viewset = CaptureViewSet()
        capture_viewset.ingest_capture(
            capture=capture,
            drf_channel=None,
            rh_scan_group=uuid.UUID(self.scan_group),
            requester=self.user,
            top_level_dir=Path(self.top_level_dir),
        )

        # Refresh index
        self.client.indices.refresh(
            index=f"{self.test_index_prefix}{self.capture.capture_type}",
        )

    def _call_replace_index(self):
        """Call replace_index command."""
        call_command(
            "replace_index",
            index_name=self.index_name,
            capture_type=self.capture_type,
        )

    def _raises_mapper_parsing_exception(
        self,
        new_index_config: dict[str, str],
    ) -> bool:
        """Put mapping on index and return True if it fails."""
        try:
            self.client.indices.put_mapping(
                index=self.index_name,
                body=new_index_config,
            )
        except RequestError as e:
            if "mapper_parsing_exception" in str(e):
                msg = f"Mapper parsing exception: {e}"
                logger.warning(msg)
                return True
        return False

    def test_successful_reindex(self) -> None:
        """Test successful reindex with matching document counts."""

        # Get initial document
        initial_response = self.client.search(
            index=self.index_name,
            body={"query": {"match": {"_id": str(self.capture.uuid)}}},
        )
        assert initial_response["hits"]["total"]["value"] == 1

        new_index_mapping = get_mapping_by_capture_type(self.capture_type)
        new_index_config = {
            "mappings": new_index_mapping,
            "settings": {
                "index": {
                    "number_of_shards": 1,
                    "number_of_replicas": 1,
                },
            },
        }

        # assert that the current index mapping is not the new mapping
        old_index_mapping = self.client.indices.get_mapping(index=self.index_name)
        assert old_index_mapping != new_index_mapping, (
            "Index mapping is already the new mapping"
        )

        # assert that the put_mapping operation fails
        # this means we need to use replace_index
        assert self._raises_mapper_parsing_exception(new_index_config), (
            "put_mapping operation should fail"
        )

        # Mock user input
        with cast(
            "mock._patch",  # noqa: SLF001 # pyright: ignore[reportPrivateUsage,reportMissingTypeArgument]
            mock.patch("builtins.input", return_value="y"),
        ):
            # Run replace_index command
            self._call_replace_index()

        # Verify document reindexed
        self.client.indices.refresh(index=self.index_name)
        after_response = self.client.search(
            index=self.index_name,
            body={"query": {"match": {"_id": str(self.capture.uuid)}}},
        )
        assert after_response["hits"]["total"]["value"] == 1, (
            "Document was not reindexed"
        )

        # Verify mapping was updated
        current_index_mapping = self.client.indices.get_mapping(index=self.index_name)[
            self.index_name
        ]["mappings"]
        assert current_index_mapping != old_index_mapping, (
            "Index mapping was not updated"
        )

        # check that the current mapping includes all the fields in the new mapping
        # exact match is unreliable because of opensearch dynamic templates

        # get the keys of the current mapping
        current_mapping_keys = set(current_index_mapping["properties"].keys())
        new_mapping_keys = set(new_index_mapping["properties"].keys())
        missing_from_current = new_mapping_keys - current_mapping_keys
        missing_from_new = current_mapping_keys - new_mapping_keys
        assert not missing_from_new, (
            "Current index mapping is missing fields from the new mapping: "
            f"{missing_from_new}"
        )
        assert not missing_from_current, (
            "Current index mapping has extra fields not in the new mapping: "
            f"{missing_from_current}"
        )
        msg = "New index mapping is correct"
        logger.debug(msg)

        # Verify metadata transformed
        doc = after_response["hits"]["hits"][0]["_source"]
        assert (
            doc["search_props"]["center_frequency"]
            == self.json_file["center_frequency"]
        )
        assert doc["search_props"]["sample_rate"] == self.json_file["sample_rate"]
        assert doc["search_props"]["coordinates"] == [
            self.json_file["longitude"],
            self.json_file["latitude"],
        ]

    def test_fail_state_reset_to_original(self) -> None:
        """Test that the reindex fails and is reset to original state."""

        initial_count = self.client.count(index=self.index_name)["count"]
        assert initial_count == 1, (
            "Initial index state should have 1 document: the test capture"
        )

        initial_mapping = self.client.indices.get_mapping(
            index=self.index_name,
        )[self.index_name]["mappings"]

        with (
            mock.patch("builtins.input", return_value="y"),
            mock.patch(
                "sds_gateway.api_methods.management.commands.replace_index.get_mapping_by_capture_type",
            ) as mock_mapping,
        ):
            # return an invalid mapping that will cause reindex to fail
            mock_mapping.return_value = {
                "properties": {
                    "capture_props": {
                        "type": "keyword",  # this conflicts with nested type
                    },
                },
            }

            self._call_replace_index()

        self.client.indices.refresh(index=self.index_name)
        final_count = self.client.count(index=self.index_name)["count"]
        final_mapping = self.client.indices.get_mapping(
            index=self.index_name,
        )[self.index_name]["mappings"]

        assert final_count == 1, "Document count should be preserved after failure"
        assert final_mapping == initial_mapping, (
            "Index mapping was not reset to original: "
            f"{initial_mapping} != {final_mapping}"
        )
        backup_indices = self.client.indices.get(index=f"{self.index_name}-backup-*")
        assert len(backup_indices) == 1, "Backup index should remain after failure"

    def test_duplicate_capture_deletion(self) -> None:
        """Test that duplicate captures are deleted."""

        # Get initial document
        initial_response = self.client.search(
            index=self.index_name,
            body={"query": {"match": {"_id": str(self.capture.uuid)}}},
        )
        assert initial_response["hits"]["total"]["value"] == 1

        # Create duplicate capture
        duplicate_capture = self._create_test_capture(self.user, self.top_level_dir)
        self._index_test_capture(duplicate_capture)

        # Verify duplicate capture was created
        duplicate_capture = (
            Capture.objects.filter(
                scan_group=self.scan_group,
                capture_type=self.capture.capture_type,
                owner=self.user,
            )
            .exclude(uuid=self.capture.uuid)
            .first()
        )
        assert duplicate_capture is not None

        # Mock user input
        with cast(
            "mock._patch",  # noqa: SLF001 # pyright: ignore[reportPrivateUsage,reportMissingTypeArgument]
            mock.patch("builtins.input", return_value="y"),
        ):
            # Run replace_index command
            self._call_replace_index()

        # Verify the scan group only has one capture
        final_response = self.client.search(
            index=self.index_name,
            body={"query": {"match": {"scan_group": self.scan_group}}},
        )
        assert final_response["hits"]["total"]["value"] == 1

    def test_no_capture_deletion_multiple_owners(self) -> None:
        """
        Test that captures with similar attributes are not deleted
        if they belong to different owners.
        """
        # Create a second user
        other_user = User.objects.create(email="otheruser@example.com")
        other_top_level_dir = f"/files/{other_user.email}/{self.scan_group}"
        expected_count = 2

        # Create a duplicate capture for the second user
        non_duplicate_capture = self._create_test_capture(
            owner=other_user,
            top_level_dir=other_top_level_dir,
        )
        self._index_test_capture(non_duplicate_capture)
        self._create_test_file(other_user)

        # Get initial document
        initial_response = self.client.search(
            index=self.index_name,
            body={"query": {"match": {"_id": str(self.capture.uuid)}}},
        )
        assert initial_response["hits"]["total"]["value"] == 1

        with mock.patch("builtins.input", return_value="y"):
            # Run replace_index command
            self._call_replace_index()

        # Verify the scan group has two captures
        final_response = self.client.search(
            index=self.index_name,
            body={"query": {"match": {"scan_group": self.scan_group}}},
        )
        assert final_response["hits"]["total"]["value"] == expected_count

        # Verify that there is only one capture per owner
        # (checking top_level_dir which contains owner in the path)
        for hit in final_response["hits"]["hits"]:
            assert hit["_source"]["top_level_dir"] in [
                self.top_level_dir,
                other_top_level_dir,
            ]


class OpenSearchDRFIndexResetTest(APITestCase):
    def setUp(self) -> None:
        self.client = get_opensearch_client()
        self.capture_type = CaptureType.DigitalRF
        self.test_index_prefix = "captures-test-"
        self.index_name = f"{self.test_index_prefix}{self.capture_type}"

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
                        "sample_rate_numerator": {"type": "long"},
                        "sample_rate_denominator": {"type": "long"},
                        "samples_per_second": {"type": "long"},
                        "start_bound": {"type": "long"},
                        "end_bound": {"type": "long"},
                        "init_utc_timestamp": {"type": "integer"},
                        "computer_time": {"type": "integer"},
                        "uuid_str": {"type": "keyword"},
                        "center_freq": {"type": "double"},
                        "span": {"type": "integer"},
                        "gain": {"type": "float"},
                        "bandwidth": {"type": "integer"},
                        "antenna": {"type": "text"},
                        "indoor_outdoor": {"type": "keyword"},
                        "antenna_direction": {"type": "float"},
                        "custom_attrs": {"type": "nested"},
                    },
                },
                # Intentionally omitting search_props to test migration
            },
        }

        self.user = User.objects.create(email="testuser@example.com")
        self.channel = "test_channel"
        self.top_level_dir = f"/files/{self.user.email}/{self.channel}"

        # setup test data and create initial capture
        self._setup_test_data()
        self.capture = self._create_test_capture(self.user, self.top_level_dir)
        self._initialize_test_index()
        self._index_test_capture(self.capture)

    def tearDown(self) -> None:
        """Clean up test data."""
        # delete test indices
        self.client.indices.delete(
            index=f"{self.test_index_prefix}*",
            ignore_unavailable=True,  # pyright: ignore[reportCallIssue]
        )

        # clean up test objects in correct order
        self.user.captures.all().delete()
        self.user.delete()

    def _setup_test_data(self):
        """Setup test data for DRF capture."""
        # Create DRF metadata JSON with test data
        self.json_file = {
            "H5Tget_class": 1,
            "H5Tget_size": 8,
            "H5Tget_order": 0,
            "H5Tget_precision": 64,
            "H5Tget_offset": 0,
            "subdir_cadence_secs": 3600,
            "file_cadence_millisecs": 1000,
            "sample_rate_numerator": 24000000,
            "sample_rate_denominator": 1,
            "samples_per_second": 24000000,
            "start_bound": 1705000000,
            "end_bound": 1705003600,
            "is_complex": True,
            "is_continuous": True,
            "epoch": "1970-01-01T00:00:00Z",
            "digital_rf_time_description": "Unix time",
            "digital_rf_version": "0.10.0",
            "sequence_num": 1,
            "init_utc_timestamp": 1705000000,
            "computer_time": 1705000000,
            "uuid_str": str(uuid.uuid4()),
            "center_freq": 2000000000,
            "span": 20000000,
            "gain": 1.0,
            "bandwidth": 1000000,
            "antenna": "Test Antenna",
            "indoor_outdoor": "indoor",
            "antenna_direction": 0.0,
            "custom_attrs": {"test_attr": "test_value"},
        }

    def _create_test_capture(self, owner: User, top_level_dir: str):
        """Create and index a test capture."""
        return Capture.objects.create(
            owner=owner,
            channel=self.channel,
            capture_type=self.capture_type,
            index_name=self.index_name,
            top_level_dir=top_level_dir,
        )

    def _initialize_test_index(self) -> None:
        """Initialize test index with mapping."""
        # initialize test index with old mapping
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

    # for drf tests, skip file validation to avoid dealing with HDF5 files
    def _mock_metadata_validation(self) -> "mock._patch":  # pyright: ignore[reportPrivateUsage, reportMissingTypeArgument]
        """Mock metadata validation."""
        return mock.patch(
            "sds_gateway.api_methods.views.capture_endpoints.validate_metadata_by_channel",
            return_value=self.json_file,
        )

    def _call_replace_index(self) -> None:
        """Call replace_index command."""
        logger.debug(
            "Calling 'replace_index' for index "
            f"'{self.index_name}' and '{self.capture_type}'",
        )
        call_command(
            "replace_index",
            index_name=self.index_name,
            capture_type=self.capture_type,
        )

    def _index_test_capture(self, capture: Capture) -> None:
        """Index test capture metadata."""
        capture_viewset = CaptureViewSet()

        # Mock metadata validation
        with self._mock_metadata_validation():
            capture_viewset.ingest_capture(
                capture=capture,
                drf_channel=self.channel,
                rh_scan_group=None,
                requester=self.user,
                top_level_dir=Path(self.top_level_dir),
            )

        # Refresh index
        self.client.indices.refresh(index=self.index_name)

    def _raises_mapper_parsing_exception(
        self,
        new_index_config: dict[str, str],
    ) -> bool:
        """Put mapping on index and return True if it fails."""
        try:
            self.client.indices.put_mapping(
                index=self.index_name,
                body=new_index_config,
            )
        except RequestError as e:
            if "mapper_parsing_exception" in str(e):
                msg = f"Mapper parsing exception: {e}"
                logger.warning(msg)
                return True
        return False

    def test_successful_reindex(self) -> None:
        """Test successful reindex with matching document counts."""

        # Get initial document
        initial_response = self.client.search(
            index=self.index_name,
            body={"query": {"match": {"_id": str(self.capture.uuid)}}},
        )
        assert initial_response["hits"]["total"]["value"] == 1

        new_index_mapping = get_mapping_by_capture_type(self.capture_type)
        new_index_config = {
            "mappings": new_index_mapping,
            "settings": {
                "index": {
                    "number_of_shards": 1,
                    "number_of_replicas": 1,
                },
            },
        }

        # assert that the current index mapping is not the new mapping
        old_index_mapping = self.client.indices.get_mapping(index=self.index_name)
        assert old_index_mapping != new_index_mapping, (
            "Index mapping is already the new mapping"
        )

        # assert that the put_mapping operation fails
        # this means we need to use replace_index
        assert self._raises_mapper_parsing_exception(new_index_config), (
            "put_mapping operation should fail"
        )

        # Mock user input
        with (
            mock.patch("builtins.input", return_value="y"),
            self._mock_metadata_validation(),
        ):
            # Run replace_index command
            logger.debug("Calling 'replace_index' command")
            self._call_replace_index()

        # Verify document reindexed
        self.client.indices.refresh(index=self.index_name)
        after_response = self.client.search(
            index=self.index_name,
            body={"query": {"match": {"_id": str(self.capture.uuid)}}},
        )
        assert after_response["hits"]["total"]["value"] == 1, (
            "Document was not reindexed"
        )

        # verify mapping was updated
        current_index_mapping = self.client.indices.get_mapping(index=self.index_name)[
            self.index_name
        ]["mappings"]
        assert current_index_mapping != old_index_mapping, (
            "Index mapping was not updated"
        )

        # check that the current mapping includes all the fields in the new mapping
        # exact match is unreliable because of opensearch dynamic templates

        # get the keys of the current mapping
        _current_mapping_keys = set(current_index_mapping["properties"].keys())
        _new_mapping_keys = set(new_index_mapping["properties"].keys())
        missing_from_current = _new_mapping_keys - _current_mapping_keys
        missing_from_new = _current_mapping_keys - _new_mapping_keys

        # ASSERT the current mapping includes all the fields in the new mapping
        assert not missing_from_current, (
            f"Missing fields in current mapping: {missing_from_current}"
        )
        assert not missing_from_new, (
            f"Extra fields in current mapping: {missing_from_new}"
        )

        msg = "New index mapping is correct"
        logger.debug(msg)

        # ASSERT metadata is transformed
        doc = after_response["hits"]["hits"][0]["_source"]
        assert doc["search_props"]["center_frequency"] == self.json_file["center_freq"]
        assert doc["search_props"]["sample_rate"] == (
            self.json_file["sample_rate_numerator"]
            / self.json_file["sample_rate_denominator"]
        )
        assert doc["search_props"]["frequency_min"] == self.json_file["center_freq"] - (
            self.json_file["span"] / 2
        )
        assert doc["search_props"]["frequency_max"] == self.json_file["center_freq"] + (
            self.json_file["span"] / 2
        )
        assert doc["search_props"]["start_time"] == self.json_file["start_bound"]
        assert doc["search_props"]["end_time"] == self.json_file["end_bound"]

    def test_fail_state_reset_to_original(self) -> None:
        """Test that the reindex fails and is reset to original state."""

        initial_count = self.client.count(index=self.index_name)["count"]
        assert initial_count == 1, (
            "Initial index state should have 1 document: the test capture"
        )

        initial_mapping = self.client.indices.get_mapping(
            index=self.index_name,
        )[self.index_name]["mappings"]

        with (
            mock.patch("builtins.input", return_value="y"),
            mock.patch(
                "sds_gateway.api_methods.management.commands.replace_index.get_mapping_by_capture_type",
            ) as mock_mapping,
            self._mock_metadata_validation(),
        ):
            # return an invalid mapping that will cause reindex to fail
            mock_mapping.return_value = {
                "properties": {
                    "capture_props": {
                        "type": "keyword",  # this conflicts with nested type
                    },
                },
            }

            # run replace_index command
            self._call_replace_index()

        # verify final state
        self.client.indices.refresh(index=self.index_name)
        final_count = self.client.count(index=self.index_name)["count"]
        final_mapping = self.client.indices.get_mapping(
            index=self.index_name,
        )[self.index_name]["mappings"]
        backup_indices = self.client.indices.get(index=f"{self.index_name}-backup-*")

        assert final_count == 1, "Document count should be preserved after failure"
        assert final_mapping == initial_mapping, (
            "Index mapping was not reset to original"
        )
        assert len(backup_indices) == 1, "Backup index should remain after failure"

    def test_duplicate_capture_deletion(self) -> None:
        """Test that duplicate captures are deleted."""

        # Get initial document
        initial_response = self.client.search(
            index=self.index_name,
            body={"query": {"match": {"_id": str(self.capture.uuid)}}},
        )
        assert initial_response["hits"]["total"]["value"] == 1

        # Create duplicate capture
        duplicate_capture = self._create_test_capture(self.user, self.top_level_dir)
        self._index_test_capture(duplicate_capture)

        # Verify duplicate capture was created
        duplicate_capture = (
            Capture.objects.filter(
                channel=self.channel,
                capture_type=self.capture.capture_type,
                owner=self.user,
            )
            .exclude(uuid=self.capture.uuid)
            .first()
        )
        assert duplicate_capture is not None

        # Mock user input and metadata validation
        with (
            mock.patch("builtins.input", return_value="y"),
            self._mock_metadata_validation(),
        ):
            # Run replace_index command
            self._call_replace_index()

        # Verify the channel only has one capture
        final_response = self.client.search(
            index=self.index_name,
            body={"query": {"match": {"channel": self.channel}}},
        )
        assert final_response["hits"]["total"]["value"] == 1

    def test_no_capture_deletion_multiple_owners(self) -> None:
        """
        Test that captures with similar attributes are not deleted
        if they belong to different owners.
        """
        # Create a second user
        other_user = User.objects.create(email="otheruser@example.com")
        other_top_level_dir = f"/files/{other_user.email}/{self.channel}"
        expected_count = 2
        # Create a duplicate capture for the second user
        duplicate_capture = self._create_test_capture(other_user, other_top_level_dir)
        self._index_test_capture(duplicate_capture)

        # Get initial document
        initial_response = self.client.search(
            index=self.index_name,
            body={"query": {"match": {"_id": str(self.capture.uuid)}}},
        )
        assert initial_response["hits"]["total"]["value"] == 1

        # Mock user input and metadata validation
        with (
            mock.patch("builtins.input", return_value="y"),
            self._mock_metadata_validation(),
        ):
            # Run replace_index command
            self._call_replace_index()

        # Verify the channel has two captures
        final_response = self.client.search(
            index=self.index_name,
            body={"query": {"match": {"channel": self.channel}}},
        )
        assert final_response["hits"]["total"]["value"] == expected_count

        # Verify that there is only one capture per owner
        # (checking top_level_dir which contains owner in the path)
        for hit in final_response["hits"]["hits"]:
            assert hit["_source"]["top_level_dir"] in [
                self.top_level_dir,
                other_top_level_dir,
            ]
