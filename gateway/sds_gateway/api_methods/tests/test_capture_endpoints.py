"""Tests for capture endpoints."""

import datetime
import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from typing import cast
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from opensearchpy import exceptions as os_exceptions
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.test import APITestCase

from sds_gateway.api_methods.helpers.index_handling import index_capture_metadata
from sds_gateway.api_methods.helpers.reconstruct_file_tree import (
    _get_list_of_capture_files,
)
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.tests.factories import UserSharePermissionFactory
from sds_gateway.api_methods.utils.metadata_schemas import get_mapping_by_capture_type
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.users.models import UserAPIKey

# Test constants
TEST_USER_PASSWORD = "testpass123"  # noqa: S105

if TYPE_CHECKING:
    from rest_framework_api_key.models import AbstractAPIKey


User = get_user_model()

# Constants
TOTAL_TEST_CAPTURES = 3

logger = logging.getLogger(__name__)


class CaptureTestCases(APITestCase):
    def setUp(self) -> None:
        """Set up test data."""
        # bootstrapping instance attributes
        self.test_index_prefix = "captures-test"
        self.opensearch = get_opensearch_client()

        # set up test metadata checks
        self.center_freq = 2_000_000_000.0
        self.drf_capture_count = 2
        self.rh_capture_count = 1

        # clean up any existing test indices
        self._cleanup_opensearch_test_indices()

        # set up new test data
        self.client = APIClient()
        self.scan_group = uuid.uuid4()
        self.channel_v0 = "ch0"
        self.channel_v1 = "ch1"
        self.top_level_dir_v0 = "test-dir-drf-v0"
        self.top_level_dir_v1 = "test-dir-drf-v1"
        self.top_level_dir_rh = "test-dir-rh"
        self.user = User.objects.create(
            email="testuser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,  # allows creating API keys
        )

        # Create API key for authentication
        api_key, key = UserAPIKey.objects.create_key(
            name="test-key",
            user=self.user,
        )
        self.api_key = cast("AbstractAPIKey", api_key)
        self.key = cast("str", key)
        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key: {self.key}")

        # Set up API endpoints
        self.list_url = reverse("api:captures-list")
        self.detail_url = lambda uuid: reverse(
            "api:captures-detail",
            kwargs={"pk": uuid},
        )

        # Create test captures without metadata
        self.drf_capture_v0 = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel=self.channel_v0,
            index_name=f"{self.test_index_prefix}-drf",
            owner=self.user,
            top_level_dir=self.top_level_dir_v0,
        )

        self.drf_capture_v1 = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel=self.channel_v1,
            index_name=f"{self.test_index_prefix}-drf",
            owner=self.user,
            top_level_dir=self.top_level_dir_v1,
        )

        self.rh_capture = Capture.objects.create(
            capture_type=CaptureType.RadioHound,
            index_name=f"{self.test_index_prefix}-rh",
            owner=self.user,
            scan_group=self.scan_group,
            top_level_dir=self.top_level_dir_rh,
        )

        # Define test metadata
        self.drf_metadata_v0 = {
            "center_freq": int(self.center_freq),
            "bandwidth": 20_000_000,
            "gain": 20.5,
        }

        # uses MEP metadata format
        self.drf_metadata_v1 = {
            "center_frequencies": [self.center_freq],
            "bandwidth": 20_000_000,
            "gain": 20.5,
        }

        self.rh_metadata = {
            "altitude": 2.0,
            "batch": 0,
            "center_frequency": self.center_freq,
            "scan_group": str(self.scan_group),
            "custom_fields": {
                "requested": {
                    "fmax": 2_010_000_000,
                    "fmin": 1_990_000_000,
                    "gain": 1,
                    "samples": 1024,
                    "span": 20_000_000,
                },
            },
            "gain": 1.0,
            "hardware_board_id": "025",
            "hardware_version": "3.4",
            "latitude": 41.699584,
            "longitude": -86.237237,
            "mac_address": "f4e11ea46780",
            "metadata": {
                "archive_result": True,
                "data_type": "periodogram",
                "fmax": 2_012_000_000,
                "fmin": 1_988_000_000,
                "gps_lock": False,
                "nfft": 1024,
                "scan_time": 0.07766938209533691,
            },
            "sample_rate": 24_000_000,
            "short_name": "WI-Lab V3.4-025 #6",
            "software_version": "v0.10b30",
            "timestamp": "2025-01-10T15:48:07.100486Z",
            "type": "float32",
            "version": "v0",
        }

        # make sure indices exist
        self._setup_opensearch_indices()
        self._index_test_metadata()

    def _cleanup_opensearch_test_indices(self) -> None:
        """Clean up OpenSearch documents from tests."""
        if not hasattr(self, "opensearch"):
            self.opensearch = get_opensearch_client()
        self.opensearch.indices.delete(
            index=f"{self.test_index_prefix}*",
            ignore_unavailable=True,  # pyright: ignore[reportCallIssue]
        )

    def _setup_opensearch_indices(self) -> None:
        """Set up OpenSearch indices with proper mappings."""
        for capture, metadata_type in [
            (self.drf_capture_v0, CaptureType.DigitalRF),
            (self.drf_capture_v1, CaptureType.DigitalRF),
            (self.rh_capture, CaptureType.RadioHound),
        ]:
            assert capture.index_name, "Test capture is missing index_name."
            if not self.opensearch.indices.exists(index=capture.index_name):
                self.opensearch.indices.create(
                    index=capture.index_name,
                    body={
                        "settings": {
                            "number_of_shards": 1,
                            "number_of_replicas": 0,
                        },
                        "mappings": get_mapping_by_capture_type(metadata_type),
                    },
                )

    def _index_test_metadata(self) -> None:
        """Index test metadata into OpenSearch."""
        # Index DRF capture metadata v0
        index_capture_metadata(self.drf_capture_v0, self.drf_metadata_v0)
        self.opensearch.indices.refresh(index=self.drf_capture_v0.index_name)

        # Index DRF capture metadata v1
        index_capture_metadata(self.drf_capture_v1, self.drf_metadata_v1)
        self.opensearch.indices.refresh(index=self.drf_capture_v1.index_name)

        # Index RH capture metadata
        index_capture_metadata(self.rh_capture, self.rh_metadata)
        # Ensure immediate visibility
        self.opensearch.indices.refresh(index=self.rh_capture.index_name)

    def tearDown(self) -> None:
        """Clean up test data."""

        # Clean up OpenSearch documents
        self._cleanup_opensearch_test_indices()

        # clean up test objects in correct order
        self.user.captures.all().delete()
        self.user.delete()

    def test_create_drf_capture_v0_201(self) -> None:
        """Test creating drf capture returns metadata."""
        unique_channel = f"{self.channel_v0}_1"
        unique_top_level_dir = f"{self.top_level_dir_v0}-1"

        with (
            patch(
                "sds_gateway.api_methods.views.capture_endpoints.validate_metadata_by_channel",
                return_value=self.drf_metadata_v0,
            ),
            patch(
                "sds_gateway.api_methods.views.capture_endpoints.infer_index_name",
                return_value=self.drf_capture_v0.index_name,
            ),
        ):
            response_raw = self.client.post(
                self.list_url,
                data={
                    "capture_type": CaptureType.DigitalRF,
                    "channel": unique_channel,
                    "top_level_dir": unique_top_level_dir,
                },
            )
            assert response_raw.status_code == status.HTTP_201_CREATED, (
                f"Status {response_raw.status_code} != {status.HTTP_201_CREATED}"
            )
            response = response_raw.json()

            assert response["capture_props"] == self.drf_metadata_v0, (
                f"Props {response['capture_props']} != {self.drf_metadata_v0}"
            )
            assert response["channel"] == unique_channel, (
                f"Channel {response['channel']} != {unique_channel}"
            )
            assert response["top_level_dir"] == "/" + unique_top_level_dir, (
                "Gateway should normalize to an absolute path: "
                f"{response['top_level_dir']}"
            )
            assert response["capture_type"] == CaptureType.DigitalRF, (
                f"Capture type: {response['capture_type']} != {CaptureType.DigitalRF}"
            )
            assert (
                response["capture_props"]["center_freq"]
                == (self.drf_metadata_v0["center_freq"])
            ), (
                "Center frequency: "
                f"{response['capture_props']['center_freq']} "
                f"!= {self.drf_metadata_v0['center_freq']}"
            )

    def test_create_drf_capture_v1_201(self) -> None:
        """Test creating drf capture returns metadata."""
        unique_channel = f"{self.channel_v1}_1"
        unique_top_level_dir = f"{self.top_level_dir_v1}-1"

        with (
            patch(
                "sds_gateway.api_methods.views.capture_endpoints.validate_metadata_by_channel",
                return_value=self.drf_metadata_v1,
            ),
            patch(
                "sds_gateway.api_methods.views.capture_endpoints.infer_index_name",
                return_value=self.drf_capture_v1.index_name,
            ),
        ):
            response_raw = self.client.post(
                self.list_url,
                data={
                    "capture_type": CaptureType.DigitalRF,
                    "channel": unique_channel,
                    "top_level_dir": unique_top_level_dir,
                },
            )
            assert response_raw.status_code == status.HTTP_201_CREATED, (
                f"Status {response_raw.status_code} != {status.HTTP_201_CREATED}"
            )
            response = response_raw.json()

            assert response["capture_props"] == self.drf_metadata_v1, (
                f"Props {response['capture_props']} != {self.drf_metadata_v1}"
            )
            assert response["channel"] == unique_channel, (
                f"Channel {response['channel']} != {unique_channel}"
            )
            assert response["top_level_dir"] == "/" + unique_top_level_dir, (
                "Gateway should normalize to an absolute path: "
                f"{response['top_level_dir']}"
            )
            assert response["capture_type"] == CaptureType.DigitalRF, (
                f"Capture type: {response['capture_type']} != {CaptureType.DigitalRF}"
            )
            assert isinstance(response["capture_props"]["center_frequencies"], list), (
                "Center frequencies should be a list"
            )
            assert (
                response["capture_props"]["center_frequencies"]
                == self.drf_metadata_v1["center_frequencies"]
            ), (
                "Center frequencies: "
                f"{response['capture_props']['center_frequencies']} "
                f"!= {self.drf_metadata_v1['center_frequencies']}"
            )

    def test_create_rh_capture_201(self) -> None:
        """Test creating rh capture returns metadata."""
        unique_scan_group = uuid.uuid4()
        unique_rh_metadata = self.rh_metadata.copy()
        unique_rh_metadata["scan_group"] = str(unique_scan_group)

        with (
            patch(
                "sds_gateway.api_methods.views.capture_endpoints.find_rh_metadata_file",
                return_value="mock_path",
            ),
            patch(
                "sds_gateway.api_methods.views.capture_endpoints.load_rh_file",
                return_value=type(
                    "MockRHData",
                    (),
                    {"model_dump": lambda mode: unique_rh_metadata},
                ),
            ),
            patch(
                "sds_gateway.api_methods.views.capture_endpoints.infer_index_name",
                return_value=self.rh_capture.index_name,
            ),
        ):
            response_raw = self.client.post(
                self.list_url,
                data={
                    "capture_type": CaptureType.RadioHound,
                    "scan_group": str(unique_scan_group),
                    "top_level_dir": self.top_level_dir_rh,
                },
            )
            assert response_raw.status_code == status.HTTP_201_CREATED, (
                f"Unexpected status code: {response_raw.status_code}"
            )
            response = response_raw.json()
            assert response["scan_group"] == str(
                unique_scan_group,
            ), f"Unexpected scan group: {response['scan_group']}"
            assert response["capture_props"] == unique_rh_metadata, (
                f"{response['capture_props']} != {unique_rh_metadata}"
            )
            assert response["capture_type"] == CaptureType.RadioHound, (
                f"{response['capture_type']} != {CaptureType.RadioHound}"
            )
            assert response["top_level_dir"] == "/" + self.top_level_dir_rh, (
                f"Expected Gateway to normalize the path: {response['top_level_dir']}"
            )

    def test_create_drf_capture_already_exists(self) -> None:
        """Test creating drf capture returns metadata."""
        with (
            patch(
                "sds_gateway.api_methods.views.capture_endpoints.validate_metadata_by_channel",
                return_value=self.drf_metadata_v0,
            ),
            patch(
                "sds_gateway.api_methods.views.capture_endpoints.infer_index_name",
                return_value=self.drf_capture_v0.index_name,
            ),
        ):
            response_raw = self.client.post(
                self.list_url,
                data={
                    "capture_type": CaptureType.DigitalRF,
                    "channel": self.channel_v0,
                    "top_level_dir": self.top_level_dir_v0,
                },
            )
            assert response_raw.status_code == status.HTTP_400_BAD_REQUEST
            response = response_raw.json()
            assert (
                "channel and top level directory are already in use"
                in response["detail"]
            ), f"Unexpected error message: {response['detail']}"

    def test_create_rh_capture_scan_group_conflict(self) -> None:
        """Test creating rh capture with existing scan group returns error."""
        # ARRANGE

        with (
            patch(
                "sds_gateway.api_methods.views.capture_endpoints.find_rh_metadata_file",
                return_value="mock_path",
            ),
            patch(
                "sds_gateway.api_methods.views.capture_endpoints.load_rh_file",
                return_value=type(
                    "MockRHData",
                    (),
                    {"model_dump": lambda mode: self.rh_metadata},
                ),
            ),
            patch(
                "sds_gateway.api_methods.views.capture_endpoints.infer_index_name",
                return_value=self.rh_capture.index_name,
            ),
        ):
            # ACT
            response_raw = self.client.post(
                self.list_url,
                data={
                    "capture_type": CaptureType.RadioHound,
                    "scan_group": str(self.scan_group),
                    "top_level_dir": self.top_level_dir_rh,
                },
            )

            # ASSERT
            assert response_raw.status_code == status.HTTP_400_BAD_REQUEST, (
                f"Unexpected status code: {response_raw.status_code}"
            )
            response = response_raw.json()
            assert "scan group is already in use" in response["detail"], (
                f"Unexpected error message: {response['detail']}"
            )

    def test_update_capture_404(self) -> None:
        """Test updating a non-existent capture returns 404."""
        response = self.client.put(
            self.detail_url("00000000-0000-0000-0000-000000000000"),
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_capture_200_new_metadata(self) -> None:
        """Test updating a capture returns 200 with new metadata."""
        # update the metadata dict and insert into the capture update payload
        new_metadata = self.drf_metadata_v0.copy()
        new_metadata["center_freq"] = 1_500_000_000
        new_metadata["gain"] = 10.5

        with patch(
            "sds_gateway.api_methods.views.capture_endpoints.validate_metadata_by_channel",
            return_value=new_metadata,
        ):
            response = self.client.put(
                self.detail_url(self.drf_capture_v0.uuid),
            )
            assert response.status_code == status.HTTP_200_OK
            response_data = response.json()["capture_props"]
            assert response_data["center_freq"] == new_metadata["center_freq"]
            assert response_data["gain"] == new_metadata["gain"]

    def test_list_captures_200(self) -> None:
        """Test listing captures returns metadata for all captures."""
        response_raw = self.client.get(self.list_url)
        assert response_raw.status_code == status.HTTP_200_OK

        response = response_raw.json()
        assert all(
            field in response for field in ["count", "results", "next", "previous"]
        ), "Expected 'count', 'results', 'next', and 'previous' in response"
        assert response["count"] == TOTAL_TEST_CAPTURES, (
            f"Expected {TOTAL_TEST_CAPTURES} captures, got {response['count']}"
        )
        assert "results" in response, "Expected 'results' in response"
        results = response["results"]

        # verify drf captures
        drf_captures = [
            c for c in results if c["capture_type"] == CaptureType.DigitalRF
        ]
        assert len(drf_captures) == self.drf_capture_count, (
            f"Expected {self.drf_capture_count} DRF captures, got {len(drf_captures)}"
        )
        for drf_capture in drf_captures:
            if "center_freq" in drf_capture["capture_props"]:
                assert drf_capture["capture_props"]["center_freq"] == self.center_freq
                assert drf_capture["channel"] == self.channel_v0
                assert drf_capture["top_level_dir"] == self.top_level_dir_v0
            else:
                assert (
                    drf_capture["capture_props"]["center_frequencies"][0]
                    == self.center_freq
                )
                assert drf_capture["channel"] == self.channel_v1
                assert drf_capture["top_level_dir"] == self.top_level_dir_v1

        # verify rh capture
        rh_capture = next(
            c for c in results if c["capture_type"] == CaptureType.RadioHound
        )

        assert rh_capture["capture_props"] == self.rh_metadata, (
            f"Expected {self.rh_metadata}, got {rh_capture['capture_props']}"
        )

        # verify other fields are present
        assert rh_capture["channel"] == "", "Expected empty channel for RH capture"
        assert rh_capture["top_level_dir"] == self.top_level_dir_rh, (
            f"Expected top level dir {self.top_level_dir_rh}, "
            f"got {rh_capture['top_level_dir']}"
        )
        assert rh_capture["scan_group"] == str(self.scan_group), (
            f"Expected scan group {self.scan_group}, got {rh_capture['scan_group']}"
        )

    def test_list_captures_by_type_200(self) -> None:
        """Test filtering captures by type returns correct metadata."""
        response_raw = self.client.get(
            f"{self.list_url}?capture_type={CaptureType.DigitalRF}",
        )
        assert response_raw.status_code == status.HTTP_200_OK

        response = response_raw.json()
        assert "count" in response, "Expected 'count' in response"
        assert response["count"] == self.drf_capture_count, (
            f"Expected count to be {self.drf_capture_count}, got {response['count']}"
        )
        assert "results" in response, "Expected 'results' in response"
        assert len(response["results"]) == self.drf_capture_count, (
            f"Expected {self.drf_capture_count} results, got {len(response['results'])}"
        )
        assert "next" in response, "Expected 'next' in response"
        assert "previous" in response, "Expected 'previous' in response"

        results = response["results"]

        assert all(
            capture["capture_type"] == CaptureType.DigitalRF for capture in results
        ), "Expected all captures to be of type DigitalRF"

        for capture in results:
            if "center_freq" in capture["capture_props"]:
                assert capture["capture_props"]["center_freq"] == self.center_freq, (
                    f"Expected center frequency {self.center_freq}, "
                    f"got {capture['capture_props']['center_freq']}"
                )
            else:
                assert (
                    capture["capture_props"]["center_frequencies"][0]
                    == self.center_freq
                ), (
                    f"Expected center frequency {self.center_freq}, "
                    f"got {capture['capture_props']['center_frequencies'][0]}"
                )

    def test_list_captures_by_invalid_type_400(self) -> None:
        """Test filtering captures by an invalid type returns 400."""
        fake_type: str = "fake_type"
        response_raw = self.client.get(f"{self.list_url}?capture_type={fake_type}")
        assert response_raw.status_code == status.HTTP_400_BAD_REQUEST
        response = response_raw.json()
        assert f"{fake_type}" in response["detail"].lower(), (
            f"Expected '{fake_type}' in error message, got {response['detail']}"
        )

    def test_list_captures_empty_list_200(self) -> None:
        """Test list captures returns 200 when no captures are accessible."""
        # delete all test user captures
        Capture.objects.filter(owner=self.user).update(
            is_deleted=True,
            deleted_at=datetime.datetime.now(datetime.UTC),
        )

        response_raw = self.client.get(self.list_url)
        assert response_raw.status_code == status.HTTP_200_OK
        response = response_raw.json()
        assert "count" in response, "Expected 'count' in response"
        assert response["count"] == 0, "Expected count to be 0"
        assert "results" in response, "Expected 'results' in response"
        assert response["results"] == [], "Expected results to be empty list"
        assert "next" in response, "Expected 'next' in response"
        assert response["next"] is None, "Expected 'next' to be None"
        assert "previous" in response, "Expected 'previous' in response"
        assert response["previous"] is None, "Expected 'previous' to be None"

    def test_list_captures_no_metadata_200(self) -> None:
        """Listing captures when metadata is missing should not fail."""
        # delete metadata from OpenSearch but keep the captures
        self.opensearch.delete_by_query(
            index=self.drf_capture_v0.index_name,
            body={
                "query": {
                    "term": {
                        "_id": str(self.drf_capture_v0.uuid),
                    },
                },
            },
        )
        # ensure changes are visible
        self.opensearch.indices.refresh(index=self.drf_capture_v0.index_name)
        response = self.client.get(self.list_url)
        assert response.status_code == status.HTTP_200_OK

    def test_list_captures_with_metadata_filters_no_type_200(self) -> None:
        """
        Test listing captures with metadata filters returns captures
        with matching metadata, without type distinction.
        """
        metadata_filters = [
            {
                "field_path": "search_props.center_frequency",
                "query_type": "match",
                "filter_value": self.center_freq,
            },
        ]

        response = self.client.get(
            f"{self.list_url}?metadata_filters={json.dumps(metadata_filters)}",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # assert that both DRF and RH captures are returned
        # with no type distinction, search_props.center_frequency is present in both
        assert data["count"] == TOTAL_TEST_CAPTURES, (
            f"Expected to find {TOTAL_TEST_CAPTURES} captures, "
            f"DRF and RH, got count: {data['count']}"
        )

        # get the DRF captures
        drf_captures = [
            c for c in data["results"] if c["capture_type"] == CaptureType.DigitalRF
        ]
        assert len(drf_captures) == self.drf_capture_count, (
            f"Expected to find {self.drf_capture_count} DRF captures, "
            f"got {len(drf_captures)}"
        )
        for drf_capture in drf_captures:
            if "center_freq" in drf_capture["capture_props"]:
                assert drf_capture["capture_props"]["center_freq"] == self.center_freq
            else:
                assert (
                    drf_capture["capture_props"]["center_frequencies"][0]
                    == self.center_freq
                )

        # get the RH capture
        rh_capture = next(
            c for c in data["results"] if c["capture_type"] == CaptureType.RadioHound
        )
        assert rh_capture["capture_props"]["center_frequency"] == self.center_freq

    def test_list_captures_with_metadata_filters_rh_200(self) -> None:
        """
        Test listing captures with metadata filters returns
        the rh capture with matching metadata.
        """
        metadata_filters = [
            {
                "field_path": "search_props.frequency_max",
                "query_type": "range",
                "filter_value": {
                    "gt": self.center_freq,
                },
            },
        ]

        with patch(
            "sds_gateway.api_methods.helpers.search_captures.infer_index_name",
            return_value=self.rh_capture.index_name,
        ):
            response = self.client.get(
                f"{self.list_url}?capture_type={CaptureType.RadioHound}&metadata_filters={json.dumps(metadata_filters)}",
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == self.rh_capture_count, (
            f"Expected to find {self.rh_capture_count} RH captures, got {data['count']}"
        )
        fmax = data["results"][0]["capture_props"]["metadata"]["fmax"]
        assert fmax > self.center_freq, (
            f"fmax should be greater than center frequency: {fmax} > {self.center_freq}"
        )

    def test_list_captures_with_metadata_filters_geolocation_200(self) -> None:
        """
        Test listing captures with metadata filters returns a
        capture with coordinates in the bounding box.
        """
        top_left_lat = 43
        top_left_lon = -87
        bottom_right_lat = 40
        bottom_right_lon = -85
        metadata_filters = [
            {
                "field_path": "search_props.coordinates",
                "query_type": "geo_bounding_box",
                "filter_value": {
                    "top_left": {
                        "lat": top_left_lat,
                        "lon": top_left_lon,
                    },
                    "bottom_right": {
                        "lat": bottom_right_lat,
                        "lon": bottom_right_lon,
                    },
                },
            },
        ]
        response = self.client.get(
            f"{self.list_url}?metadata_filters={json.dumps(metadata_filters)}",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == self.rh_capture_count, (
            f"Expected to find {self.rh_capture_count} RH captures, got {data['count']}"
        )
        latitude = data["results"][0]["capture_props"]["latitude"]
        longitude = data["results"][0]["capture_props"]["longitude"]
        assert latitude <= top_left_lat, (
            "Latitude should be less than or equal to top left latitude: "
            f"{latitude} <= {top_left_lat}"
        )
        assert longitude >= top_left_lon, (
            "Longitude should be greater than or equal to top left longitude: "
            f"{longitude} >= {top_left_lon}"
        )
        assert latitude >= bottom_right_lat, (
            "Latitude should be greater than or equal to bottom right latitude: "
            f"{latitude} >= {bottom_right_lat}"
        )
        assert longitude <= bottom_right_lon, (
            "Longitude should be less than or equal to bottom right longitude: "
            f"{longitude} <= {bottom_right_lon}"
        )

    def test_retrieve_capture_200(self) -> None:
        """Test retrieving a single capture returns full metadata."""
        response = self.client.get(self.detail_url(self.drf_capture_v0.uuid))
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["uuid"] == str(self.drf_capture_v0.uuid)
        assert data["capture_type"] == CaptureType.DigitalRF
        assert data["channel"] == self.channel_v0

        # Verify metadata is correctly retrieved for single capture
        assert data["capture_props"] == self.drf_metadata_v0

    def test_retrieve_capture_404(self) -> None:
        """Test retrieving a non-existent capture."""
        response = self.client.get(
            self.detail_url("00000000-0000-0000-0000-000000000000"),
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_not_accessible_capture_403(self) -> None:
        """Test that retrieving a capture not accessible to the user returns 403."""
        other_user = User.objects.create(
            email="otheruser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )
        other_capture = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel="other-channel",
            index_name=f"{self.test_index_prefix}-drf",
            owner=other_user,
            top_level_dir="other-dir",
        )

        response = self.client.get(self.detail_url(other_capture.uuid))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_composite_capture_functionality(self) -> None:
        """Test that multi-channel captures are returned as composite objects."""
        # Create multiple captures with the same top_level_dir to simulate multi-channel
        multi_channel_dir = "/test-multi-channel"
        expected_channel_count = 2

        # Create first capture and mark as multi-channel
        capture1 = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            index_name=f"{self.test_index_prefix}-drf",
            owner=self.user,
            top_level_dir=multi_channel_dir,
        )

        # Create second capture with same top_level_dir
        Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel="ch1",
            index_name=f"{self.test_index_prefix}-drf",
            owner=self.user,
            top_level_dir=multi_channel_dir,
        )

        # Test retrieve endpoint - should return composite
        response = self.client.get(self.detail_url(capture1.uuid))
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        # Should have channels field for composite captures
        assert "channels" in data
        assert len(data["channels"]) == expected_channel_count

        # Check that channels have the expected structure
        for channel in data["channels"]:
            assert "channel" in channel
            assert "uuid" in channel
            assert "channel_metadata" in channel

        # Test list endpoint - should also return composite
        response = self.client.get(self.list_url)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "results" in data

        # Find the composite capture in results
        composite_found = False
        for result in data["results"]:
            if result.get("top_level_dir") == multi_channel_dir:
                assert "channels" in result
                assert len(result["channels"]) == expected_channel_count
                composite_found = True
                break

        assert composite_found, "Composite capture not found in list results"

    def test_capture_name_field_functionality(self) -> None:
        """Test that the name field works correctly in captures."""
        # Test 1: Create capture with explicit name
        capture_with_name = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel="test-channel-with-name",
            index_name=f"{self.test_index_prefix}-drf",
            owner=self.user,
            top_level_dir="/test/capture/with/name",
            name="My Custom Capture Name",
        )

        # Verify the name is set correctly
        assert capture_with_name.name == "My Custom Capture Name"

        # Test string representation with name
        str_repr_with_name = str(capture_with_name)
        assert "My Custom Capture Name" in str_repr_with_name
        assert "(drf)" in str_repr_with_name  # Uses enum value, not display name

        # Test 2: Create capture without name (should auto-generate from top_level_dir)
        capture_without_name = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel="test-channel-no-name",
            index_name=f"{self.test_index_prefix}-drf",
            owner=self.user,
            top_level_dir="/test/capture/auto/generated",
        )

        # Verify the name is auto-generated from the path
        assert capture_without_name.name == "generated"

        # Test string representation with auto-generated name
        str_repr_auto = str(capture_without_name)
        assert "generated" in str_repr_auto
        assert "(drf)" in str_repr_auto  # Uses enum value, not display name

        # Test 3: Create capture with empty top_level_dir and no name
        capture_empty_path = Capture.objects.create(
            capture_type=CaptureType.RadioHound,
            index_name=f"{self.test_index_prefix}-rh",
            owner=self.user,
            scan_group=uuid.uuid4(),
            top_level_dir="",
        )

        # Should fall back to default string representation
        str_repr_empty = str(capture_empty_path)
        assert "rh capture for channel" in str_repr_empty  # Uses enum value

        # Test 4: Test API response includes name field
        response = self.client.get(self.detail_url(capture_with_name.uuid))
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "name" in data
        assert data["name"] == "My Custom Capture Name"

        # Test 5: Test list endpoint includes name field
        response = self.client.get(self.list_url)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        results = data["results"]

        # Find our test capture in the results
        test_capture = next(
            (c for c in results if c["uuid"] == str(capture_with_name.uuid)), None
        )
        assert test_capture is not None
        assert "name" in test_capture
        assert test_capture["name"] == "My Custom Capture Name"

        # Clean up test captures
        capture_with_name.delete()
        capture_without_name.delete()
        capture_empty_path.delete()

    def test_delete_capture_204(self) -> None:
        """Test deleting a capture returns 204."""
        response = self.client.delete(self.detail_url(self.drf_capture_v0.uuid))
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_soft_delete_capture_deletes_share_permissions(self) -> None:
        """
        Test that soft deleting a capture also
        soft deletes related share permissions.
        """

        # Create a test user to share with
        shared_user = User.objects.create_user(
            email="shared@example.com",
            password=TEST_USER_PASSWORD,
            name="Shared User",
        )

        # Create a capture
        capture = Capture.objects.create(
            owner=self.user,
            capture_type=CaptureType.DigitalRF,
            channel="test_channel",
            top_level_dir="/test/dir",
            index_name="test_index",
        )

        # Create a share permission for this capture
        share_permission = UserSharePermission.objects.create(
            owner=self.user,
            shared_with=shared_user,
            item_type=ItemType.CAPTURE,
            item_uuid=capture.uuid,
            is_enabled=True,
        )

        # Verify the share permission exists and is not deleted
        assert UserSharePermission.objects.filter(
            item_uuid=capture.uuid, item_type=ItemType.CAPTURE, is_deleted=False
        ).exists()

        # Soft delete the capture
        capture.soft_delete()

        # Verify the capture is soft deleted
        capture.refresh_from_db()
        assert capture.is_deleted is True

        # Verify the share permission is also soft deleted
        share_permission.refresh_from_db()
        assert share_permission.is_deleted is True

        # Verify no active share permissions exist for this capture
        assert not UserSharePermission.objects.filter(
            item_uuid=capture.uuid, item_type=ItemType.CAPTURE, is_deleted=False
        ).exists()

    def test_unified_download_capture_202(self) -> None:
        """Test that the unified download endpoint works for captures."""
        # Login the user for session authentication
        self.client.force_login(self.user)

        # Test the unified download endpoint for captures
        response = self.client.post(
            f"/users/download-item/capture/{self.drf_capture_v0.uuid}/",
        )
        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert data["success"] is True
        assert "download request accepted" in data["message"].lower()
        assert "task_id" in data
        assert data["item_name"] == self.drf_capture_v0.name or str(
            self.drf_capture_v0.uuid
        )
        assert data["user_email"] == self.user.email

    def test_unified_download_capture_invalid_type_400(self) -> None:
        """Test that the unified download endpoint rejects invalid item types."""
        # Login the user for session authentication
        self.client.force_login(self.user)

        response = self.client.post(
            f"/users/download-item/invalid_type/{self.drf_capture_v0.uuid}/",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert data["success"] is False
        assert "invalid item type" in data["message"].lower()

    def test_unified_download_capture_not_found_404(self) -> None:
        """Test that the unified download endpoint returns 404 for non-existent captures."""  # noqa: E501
        # Login the user for session authentication
        self.client.force_login(self.user)

        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = self.client.post(
            f"/users/download-item/capture/{fake_uuid}/",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["success"] is False
        assert "not found or access denied" in data["message"].lower()

    def test_directory_matching_avoids_partial_matches(self) -> None:
        """Test that directory matching doesn't match partial directory names."""

        # This test creates files in directories that could cause partial matching
        # issues:
        # - files/user_email/example/ (should match when searching for "example")
        # - files/user_email/example-fixed/ (should NOT match when searching for
        #   "example")
        # - files/user_email/rh-example/ (should match when searching for "rh-example")
        # - files/user_email/rh-example-fixed/ (should NOT match when searching for
        #   "rh-example")

        base_dir = f"files/{self.user.email}"

        # Create files in "example" directory
        example_dir = f"{base_dir}/example"
        example_file = File.objects.create(
            name="test.h5",
            directory=example_dir,
            media_type="application/octet-stream",
            size=1024,
            owner=self.user,
        )

        # Create files in "example-fixed" directory (should NOT be matched when
        # searching for "example")
        example_fixed_dir = f"{base_dir}/example-fixed"
        example_fixed_file = File.objects.create(
            name="test.h5",
            directory=example_fixed_dir,
            media_type="application/octet-stream",
            size=1024,
            owner=self.user,
        )

        # Test that searching for "example" directory only matches files in "example"
        # and its subdirectories but NOT files in "example-fixed"
        virtual_top_dir = Path(example_dir)

        # For DigitalRF, we need to create files with the channel name in the directory
        # path. Let's create files with the proper channel structure
        channel_name = "test_channel"
        example_with_channel_dir = f"{example_dir}/{channel_name}"
        example_with_channel_file = File.objects.create(
            name="test.h5",
            directory=example_with_channel_dir,
            media_type="application/octet-stream",
            size=1024,
            owner=self.user,
        )

        # Also create a file in example-fixed with the channel to test it's excluded
        example_fixed_with_channel_dir = f"{example_fixed_dir}/{channel_name}"
        example_fixed_with_channel_file = File.objects.create(
            name="test.h5",
            directory=example_fixed_with_channel_dir,
            media_type="application/octet-stream",
            size=1024,
            owner=self.user,
        )

        matching_files = _get_list_of_capture_files(
            capture_type=CaptureType.DigitalRF,
            virtual_top_dir=virtual_top_dir,
            owner=self.user,
            drf_channel=channel_name,
            verbose=True,
        )

        # Should find files in "example" directory under the channel name subdirectory
        expected_files = {
            example_with_channel_file,
        }
        actual_files = set(matching_files)

        assert actual_files == expected_files, (
            f"Expected files {expected_files}, but got {actual_files}. "
            "Files in 'example-fixed' directory should not be matched "
            "when searching for 'example'."
        )

        # Explicitly verify that ALL unwanted files are NOT included
        unwanted_files = {
            example_file,  # File in example/ without channel
            example_fixed_file,  # File in example-fixed/ without channel
            example_fixed_with_channel_file,  # File in example-fixed/ with channel
        }

        for unwanted_file in unwanted_files:
            assert unwanted_file not in actual_files, (
                f"File '{unwanted_file.name}' in directory '{unwanted_file.directory}' "
                f"should NOT be matched when searching for '{virtual_top_dir}'"
            )

        # Test RadioHound case as well
        # Create RadioHound files with similar directory names
        rh_example_dir = f"{base_dir}/rh-example"
        rh_example_file = File.objects.create(
            name="test.rh.json",
            directory=rh_example_dir,
            media_type="application/json",
            size=1024,
            owner=self.user,
        )

        rh_example_fixed_dir = f"{base_dir}/rh-example-fixed"
        rh_example_fixed_file = File.objects.create(
            name="test.rh.json",
            directory=rh_example_fixed_dir,
            media_type="application/json",
            size=1024,
            owner=self.user,
        )

        # Test RadioHound directory matching
        rh_virtual_top_dir = Path(rh_example_dir)

        rh_matching_files = _get_list_of_capture_files(
            capture_type=CaptureType.RadioHound,
            virtual_top_dir=rh_virtual_top_dir,
            owner=self.user,
            verbose=True,
        )

        # Should only find files in "rh-example" directory, not "rh-example-fixed"
        expected_rh_files = {rh_example_file}
        actual_rh_files = set(rh_matching_files)

        assert actual_rh_files == expected_rh_files, (
            f"Expected RadioHound files {expected_rh_files}, but got "
            f"{actual_rh_files}. Files in 'rh-example-fixed' directory should not be "
            "matched when searching for 'rh-example'."
        )

        # Explicitly verify that the unwanted RadioHound file is NOT included
        unwanted_rh_files = {rh_example_fixed_file}

        for unwanted_file in unwanted_rh_files:
            assert unwanted_file not in actual_rh_files, (
                f"RadioHound file '{unwanted_file.name}' in directory "
                f"'{unwanted_file.directory}' should NOT be matched when searching for "
                f"'{rh_virtual_top_dir}'"
            )

        # Clean up test files to avoid ProtectedError in tearDown
        File.objects.filter(
            owner=self.user, directory__startswith=f"files/{self.user.email}/example"
        ).delete()
        File.objects.filter(
            owner=self.user, directory__startswith=f"files/{self.user.email}/rh-example"
        ).delete()

    def test_list_captures_includes_shared_captures(self) -> None:
        """Test that list captures includes captures shared with the user."""
        
        # Create another user
        other_user = User.objects.create(
            email="otheruser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )
        
        # Create a capture owned by the other user
        shared_capture = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel="shared-channel",
            index_name=f"{self.test_index_prefix}-drf",
            owner=other_user,
            top_level_dir="shared-dir",
        )
        
        # Create a share permission for this capture using the factory
        UserSharePermissionFactory(
            owner=other_user,
            shared_with=self.user,
            item_type=ItemType.CAPTURE,
            item_uuid=shared_capture.uuid,
            is_enabled=True,
        )
        
        # List captures - should include the shared capture
        response = self.client.get(self.list_url)
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        # Should have the original captures plus the shared one
        expected_count = TOTAL_TEST_CAPTURES + 1
        assert data["count"] == expected_count, (
            f"Expected {expected_count} captures (including shared), got {data['count']}"
        )
        
        # Verify the shared capture is in the results
        shared_capture_found = False
        for capture in data["results"]:
            if capture["uuid"] == str(shared_capture.uuid):
                shared_capture_found = True
                assert capture["channel"] == "shared-channel"
                assert capture["top_level_dir"] == "shared-dir"
                break
        
        assert shared_capture_found, "Shared capture not found in list results"

    def test_retrieve_shared_capture_200(self) -> None:
        """Test that retrieving a shared capture returns 200."""
        
        # Create another user
        other_user = User.objects.create(
            email="otheruser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )
        
        # Create a capture owned by the other user
        shared_capture = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel="shared-channel",
            index_name=f"{self.test_index_prefix}-drf",
            owner=other_user,
            top_level_dir="shared-dir",
        )
        
        # Create a share permission for this capture using the factory
        UserSharePermissionFactory(
            owner=other_user,
            shared_with=self.user,
            item_type=ItemType.CAPTURE,
            item_uuid=shared_capture.uuid,
            is_enabled=True,
        )
        
        # Retrieve the shared capture
        response = self.client.get(self.detail_url(shared_capture.uuid))
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert data["uuid"] == str(shared_capture.uuid)
        assert data["channel"] == "shared-channel"
        assert data["top_level_dir"] == "shared-dir"

    def test_disabled_share_permission_blocks_access(self) -> None:
        """Test that disabled share permissions do not grant access."""
        
        # Create another user
        other_user = User.objects.create(
            email="otheruser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )
        
        # Create a capture owned by the other user
        shared_capture = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel="shared-channel",
            index_name=f"{self.test_index_prefix}-drf",
            owner=other_user,
            top_level_dir="shared-dir",
        )
        
        # Create a disabled share permission using the factory
        UserSharePermissionFactory(
            owner=other_user,
            shared_with=self.user,
            item_type=ItemType.CAPTURE,
            item_uuid=shared_capture.uuid,
            is_enabled=False,  # Disabled permission
        )
        
        # Try to retrieve the capture - should be denied
        response = self.client.get(self.detail_url(shared_capture.uuid))
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        # List captures - should not include the capture
        response = self.client.get(self.list_url)
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        # Should only have the original captures, not the shared one
        assert data["count"] == TOTAL_TEST_CAPTURES, (
            f"Expected {TOTAL_TEST_CAPTURES} captures (excluding disabled shared), got {data['count']}"
        )


class OpenSearchErrorTestCases(APITestCase):
    """Test cases for OpenSearch error handling in capture endpoints."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.user = User.objects.create(
            email="testuser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )
        api_key, key = UserAPIKey.objects.create_key(
            name="test-key",
            user=self.user,
        )

        # Create test capture without metadata
        self.mock_capture = Capture.objects.create(
            owner=self.user,
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            top_level_dir="test-dir",
        )

        self.client.credentials(HTTP_AUTHORIZATION=f"Api-Key: {key}")
        self.list_url = reverse("api:captures-list")

    @patch(
        "sds_gateway.api_methods.serializers.capture_serializers.retrieve_indexed_metadata",
    )
    def test_list_captures_opensearch_connection_error(self, mock_retrieve) -> None:
        """OpenSearch errors should be passed to clients as an internal error."""

        mock_retrieve.side_effect = os_exceptions.ConnectionError(
            "Connection refused",
        )

        response = self.client.get(self.list_url)
        mock_retrieve.assert_called_once()
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        res_json = response.json()
        assert "detail" in res_json, "'detail' field missing from failed response"
        detail = res_json["detail"]
        assert "opensearch" not in detail.lower(), f"Unexpected detail: '{detail}'"

    @patch(
        "sds_gateway.api_methods.serializers.capture_serializers.retrieve_indexed_metadata",
    )
    def test_list_captures_opensearch_request_error(self, mock_retrieve) -> None:
        """Internal OpenSearch errors should be seen as an internal error."""
        mock_retrieve.side_effect = os_exceptions.RequestError(
            "search_phase_execution_exception",
            "Invalid query",
            {"error": "Invalid query syntax"},
        )

        response = self.client.get(self.list_url)
        mock_retrieve.assert_called_once()
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        res_json = response.json()
        assert "detail" in res_json, "'detail' field missing from failed response"
        detail = res_json["detail"]
        assert "invalid query" not in detail.lower(), f"Unexpected detail: '{detail}'"

    @patch(
        "sds_gateway.api_methods.serializers.capture_serializers.retrieve_indexed_metadata",
    )
    def test_list_captures_opensearch_general_error(self, mock_retrieve) -> None:
        """OpenSearch errors should be passed to clients as an internal error."""
        mock_retrieve.side_effect = os_exceptions.OpenSearchException(
            "Unknown error occurred",
        )

        response = self.client.get(self.list_url)
        mock_retrieve.assert_called_once()
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        res_json = response.json()
        assert "detail" in res_json, "'detail' field missing from failed response"
        detail = res_json["detail"]
        assert "opensearch" not in detail.lower(), f"Unexpected detail: '{detail}'"
