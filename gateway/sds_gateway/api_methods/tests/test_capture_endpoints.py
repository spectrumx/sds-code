"""Tests for capture endpoints."""

import datetime
import json
import logging
import uuid
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
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.utils.metadata_schemas import get_mapping_by_capture_type
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.users.models import UserAPIKey

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
        """Test list captures returns 200 when no captures exist."""
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

    def test_retrieve_not_owned_capture_404(self) -> None:
        """Test that retrieving a capture not owned by the user returns 404."""

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
        assert response.status_code == status.HTTP_404_NOT_FOUND

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

    def test_delete_capture_204(self) -> None:
        """Test deleting a capture returns 204."""
        response = self.client.delete(self.detail_url(self.drf_capture_v0.uuid))
        assert response.status_code == status.HTTP_204_NO_CONTENT


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
