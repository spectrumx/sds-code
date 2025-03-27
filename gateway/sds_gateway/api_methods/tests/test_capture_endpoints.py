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

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.utils.metadata_schemas import (
    capture_index_mapping_by_type as md_props_by_type,
)
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.users.models import UserAPIKey

if TYPE_CHECKING:
    from rest_framework_api_key.models import AbstractAPIKey


User = get_user_model()

# Constants
TOTAL_TEST_CAPTURES = 2

logger = logging.getLogger(__name__)


class CaptureTestCases(APITestCase):
    def setUp(self) -> None:
        """Set up test data."""
        # First clean up any existing test data
        self._cleanup_opensearch_documents()

        # Then set up new test data
        self.client = APIClient()
        self.scan_group = uuid.uuid4()
        self.channel = "ch0"
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
        self.drf_capture = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel=self.channel,
            index_name="captures-drf",
            owner=self.user,
            top_level_dir="test-dir-drf",
        )

        self.rh_capture = Capture.objects.create(
            capture_type=CaptureType.RadioHound,
            index_name="captures-rh",
            owner=self.user,
            scan_group=self.scan_group,
            top_level_dir="test-dir-rh",
        )

        # Define test metadata
        self.drf_metadata = {
            "center_freq": 2000000000,
            "bandwidth": 20000000,
            "gain": 20.5,
        }

        self.rh_metadata = {
            "altitude": 2.0,
            "batch": 0,
            "center_frequency": 2000000000.0,
            "scan_group": str(self.scan_group),
            "custom_fields": {
                "requested": {
                    "fmax": 2010000000,
                    "fmin": 1990000000,
                    "gain": 1,
                    "samples": 1024,
                    "span": 20000000,
                },
            },
            "gain": 1.0,
            "hardware_board_id": "025",
            "hardware_version": "3.4",
            "coordinates": {
                "lat": 41.699584,
                "lon": -86.237237,
            },
            "mac_address": "f4e11ea46780",
            "metadata": {
                "archive_result": True,
                "data_type": "periodogram",
                "fmax": 2012000000,
                "fmin": 1988000000,
                "gps_lock": False,
                "nfft": 1024,
                "scan_time": 0.07766938209533691,
            },
            "sample_rate": 24000000,
            "short_name": "WI-Lab V3.4-025 #6",
            "software_version": "v0.10b30",
            "timestamp": "2025-01-10T15:48:07.100486Z",
            "type": "float32",
            "version": "v0",
        }

        # Get OpenSearch client and ensure indices exist
        self.opensearch = get_opensearch_client()
        self._setup_opensearch_indices()
        self._index_test_metadata()

    def _cleanup_opensearch_documents(self) -> None:
        """Clean up OpenSearch documents."""
        test_captures = [
            getattr(self, "drf_capture", None),
            getattr(self, "rh_capture", None),
        ]
        for capture in test_captures:
            if capture:
                try:
                    self.opensearch.delete_by_query(
                        index=capture.index_name,
                        body={
                            "query": {
                                "term": {
                                    "_id": str(capture.uuid),
                                },
                            },
                        },
                        refresh=True,  # pyright: ignore[reportCallIssue]
                        conflicts="proceed",  # pyright: ignore[reportCallIssue]
                    )
                    self.opensearch.indices.refresh(index=capture.index_name)

                except os_exceptions.OpenSearchException as e:
                    logger.debug("Error cleaning up test documents: %s", e)

    def _setup_opensearch_indices(self) -> None:
        """Set up OpenSearch indices with proper mappings."""
        for capture, metadata_type in [
            (self.drf_capture, CaptureType.DigitalRF),
            (self.rh_capture, CaptureType.RadioHound),
        ]:
            assert capture.index_name, "Test capture is missing index_name."
            if not self.opensearch.indices.exists(index=capture.index_name):
                # Create mapping without supports_range field
                mapping_properties = {}
                for field, config in md_props_by_type[metadata_type].items():
                    mapping_properties[field] = {"type": config["type"]}

                self.opensearch.indices.create(
                    index=capture.index_name,
                    body={
                        "settings": {
                            "number_of_shards": 1,
                            "number_of_replicas": 0,
                        },
                        "mappings": {
                            "properties": {
                                "channel": {"type": "keyword"},
                                "capture_type": {"type": "keyword"},
                                "created_at": {"type": "date"},
                                "capture_props": {
                                    "type": "nested",
                                    "properties": mapping_properties,
                                },
                            },
                        },
                    },
                )

    def _index_test_metadata(self) -> None:
        """Index test metadata into OpenSearch."""
        # Index DRF capture metadata
        self.opensearch.index(
            index=self.drf_capture.index_name,
            id=str(self.drf_capture.uuid),
            body={
                "channel": self.drf_capture.channel,
                "capture_type": self.drf_capture.capture_type,
                "created_at": self.drf_capture.created_at,
                "capture_props": self.drf_metadata,
            },
            version=1,  # pyright: ignore[reportCallIssue]
            version_type="external",  # pyright: ignore[reportCallIssue]
        )
        self.opensearch.indices.refresh(index=self.drf_capture.index_name)

        # Index RH capture metadata
        self.opensearch.index(
            index=self.rh_capture.index_name,
            id=str(self.rh_capture.uuid),
            body={
                "channel": self.rh_capture.channel,
                "capture_type": self.rh_capture.capture_type,
                "created_at": self.rh_capture.created_at,
                "capture_props": self.rh_metadata,
            },
        )
        # Ensure immediate visibility
        self.opensearch.indices.refresh(index=self.rh_capture.index_name)

    def tearDown(self) -> None:
        """Clean up test data."""
        super().tearDown()

        # Clean up OpenSearch documents
        self._cleanup_opensearch_documents()

    def test_create_drf_capture_201(self) -> None:
        """Test creating drf capture returns metadata."""
        unique_channel = "ch1"
        unique_top_level_dir = "test-dir-drf-1"

        with patch(
            "sds_gateway.api_methods.views.capture_endpoints.validate_metadata_by_channel",
            return_value=self.drf_metadata,
        ):
            response = self.client.post(
                self.list_url,
                data={
                    "capture_type": CaptureType.DigitalRF,
                    "channel": unique_channel,
                    "top_level_dir": unique_top_level_dir,
                    "index_name": "captures-drf",
                },
            )
            assert response.status_code == status.HTTP_201_CREATED
            assert response.json()["capture_props"] == self.drf_metadata
            assert response.json()["channel"] == unique_channel
            assert response.json()["top_level_dir"] == unique_top_level_dir
            assert response.json()["capture_type"] == CaptureType.DigitalRF

    def test_create_rh_capture_201(self) -> None:
        """Test creating rh capture returns metadata."""
        unique_scan_group = uuid.uuid4()
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
        ):
            response = self.client.post(
                self.list_url,
                data={
                    "capture_type": CaptureType.RadioHound,
                    "scan_group": str(unique_scan_group),
                    "index_name": "captures-rh",
                    "top_level_dir": "test-dir-rh",
                },
            )
            assert response.status_code == status.HTTP_201_CREATED
            assert response.json()["capture_props"] == self.rh_metadata
            assert response.json()["capture_type"] == CaptureType.RadioHound
            assert (
                response.json()["top_level_dir"]
                == "/files/testuser@example.com/test-dir"
            )

    def test_create_drf_capture_already_exists(self) -> None:
        """Test creating drf capture returns metadata."""
        with patch(
            "sds_gateway.api_methods.views.capture_endpoints.validate_metadata_by_channel",
            return_value=self.drf_metadata,
        ):
            response = self.client.post(
                self.list_url,
                data={
                    "capture_type": CaptureType.DigitalRF,
                    "channel": self.channel,
                    "top_level_dir": "test-dir-drf",
                    "index_name": "captures-drf",
                },
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert response.json()["channel"] == [
                "This channel and top level directory are already in use."
            ]

    def test_create_rh_capture_already_exists(self) -> None:
        """Test creating rh capture returns metadata."""
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
        ):
            response = self.client.post(
                self.list_url,
                data={
                    "capture_type": CaptureType.RadioHound,
                    "scan_group": str(self.scan_group),
                    "index_name": "captures-rh",
                    "top_level_dir": "test-dir-rh",
                },
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            assert response.json()["scan_group"] == [
                "This scan group is already in use."
            ]

    def test_update_capture_404(self) -> None:
        """Test updating a non-existent capture returns 404."""
        response = self.client.put(
            self.detail_url("00000000-0000-0000-0000-000000000000"),
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_update_capture_200_new_metadata(self) -> None:
        """Test updating a capture returns 200 with new metadata."""
        # update the metadata dict and insert into the capture update payload
        new_metadata = self.drf_metadata.copy()
        new_metadata["center_freq"] = 1500000000
        new_metadata["gain"] = 10.5

        with patch(
            "sds_gateway.api_methods.views.capture_endpoints.validate_metadata_by_channel",
            return_value=new_metadata,
        ):
            response = self.client.put(
                self.detail_url(self.drf_capture.uuid),
            )
            assert response.status_code == status.HTTP_200_OK
            response_data = response.json()["capture_props"]
            assert response_data["center_freq"] == new_metadata["center_freq"]
            assert response_data["gain"] == new_metadata["gain"]

    def test_list_captures_200(self) -> None:
        """Test listing captures returns metadata for all captures."""
        response = self.client.get(self.list_url)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert len(data) == TOTAL_TEST_CAPTURES

        # Verify metadata for each capture type is correctly retrieved in bulk
        drf_capture = next(
            c for c in data if c["capture_type"] == CaptureType.DigitalRF
        )
        rh_capture = next(
            c for c in data if c["capture_type"] == CaptureType.RadioHound
        )

        # Verify the metadata matches what was indexed
        assert drf_capture["capture_props"] == self.drf_metadata
        assert rh_capture["capture_props"] == self.rh_metadata

        # Verify other fields are present
        assert drf_capture["channel"] == "ch0"
        assert drf_capture["top_level_dir"] == "test-dir"
        assert rh_capture["channel"] == ""

    def test_list_captures_by_type_200(self) -> None:
        """Test filtering captures by type returns correct metadata."""
        response = self.client.get(
            f"{self.list_url}?capture_type={CaptureType.DigitalRF}",
        )
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert len(data) == 1
        assert data[0]["capture_type"] == CaptureType.DigitalRF

        # Verify metadata is correctly retrieved for filtered list
        assert data[0]["capture_props"] == self.drf_metadata
        assert data[0]["channel"] == "ch0"

    def test_list_captures_by_type_empty_list_200(self) -> None:
        """Test filtering captures by type that doesn't exist returns empty list."""
        response = self.client.get(f"{self.list_url}?capture_type=fake_type")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

    def test_list_captures_empty_list_200(self) -> None:
        """Test list captures returns 200 when no captures exist."""
        # delete all test user captures
        Capture.objects.filter(owner=self.user).update(
            is_deleted=True,
            deleted_at=datetime.datetime.now(datetime.UTC),
        )

        response = self.client.get(self.list_url)
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == [], "Expected no captures"

    def test_list_captures_no_metadata_200(self) -> None:
        """Listing captures when metadata is missing should not fail."""
        # delete metadata from OpenSearch but keep the captures
        self.opensearch.delete_by_query(
            index=self.drf_capture.index_name,
            body={
                "query": {
                    "term": {
                        "_id": str(self.drf_capture.uuid),
                    },
                },
            },
        )
        # ensure changes are visible
        self.opensearch.indices.refresh(index=self.drf_capture.index_name)
        response = self.client.get(self.list_url)
        assert response.status_code == status.HTTP_200_OK

    def test_list_captures_with_metadata_filters_no_type_200(self) -> None:
        """
        Test listing captures with metadata filters returns captures
        with matching metadata, without type distinction.
        """
        center_freq = 2000000000
        metadata_filters = [
            {
                "field_path": "capture_props.center_freq",
                "query_type": "match",
                "filter_value": center_freq,
            },
        ]
        response = self.client.get(
            f"{self.list_url}?metadata_filters={json.dumps(metadata_filters)}",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == 1, "Expected to find the DRF capture"
        returned_center_freq = data["results"][0]["capture_props"]["center_freq"]
        assert returned_center_freq == center_freq, (
            "Center frequency should be equal to the filter value: "
            f"{returned_center_freq} == {center_freq}"
        )

    def test_list_captures_with_metadata_filters_rh_200(self) -> None:
        """
        Test listing captures with metadata filters returns
        the rh capture with matching metadata.
        """
        center_freq = 2000000000
        metadata_filters = [
            {
                "field_path": "capture_props.metadata.fmax",
                "query_type": "range",
                "filter_value": {
                    "gt": center_freq,
                },
            },
        ]
        response = self.client.get(
            f"{self.list_url}?capture_type={CaptureType.RadioHound}&metadata_filters={json.dumps(metadata_filters)}",
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["count"] == 1, "Expected to find the RH capture"
        fmax = data["results"][0]["capture_props"]["metadata"]["fmax"]
        assert fmax > center_freq, (
            f"fmax should be greater than center frequency: {fmax} > {center_freq}"
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
                "field_path": "capture_props.coordinates",
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
        assert data["count"] == 1, "Expected to find the RH capture"
        coordinates = data["results"][0]["capture_props"]["coordinates"]
        assert coordinates["lat"] <= top_left_lat, (
            "Latitude should be less than or equal to top left latitude: "
            f"{coordinates['lat']} <= {top_left_lat}"
        )
        assert coordinates["lon"] >= top_left_lon, (
            "Longitude should be greater than or equal to top left longitude: "
            f"{coordinates['lon']} >= {top_left_lon}"
        )
        assert coordinates["lat"] >= bottom_right_lat, (
            "Latitude should be greater than or equal to bottom right latitude: "
            f"{coordinates['lat']} >= {bottom_right_lat}"
        )
        assert coordinates["lon"] <= bottom_right_lon, (
            "Longitude should be less than or equal to bottom right longitude: "
            f"{coordinates['lon']} <= {bottom_right_lon}"
        )

    def test_retrieve_capture_200(self) -> None:
        """Test retrieving a single capture returns full metadata."""
        response = self.client.get(self.detail_url(self.drf_capture.uuid))
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["uuid"] == str(self.drf_capture.uuid)
        assert data["capture_type"] == CaptureType.DigitalRF
        assert data["channel"] == "ch0"

        # Verify metadata is correctly retrieved for single capture
        assert data["capture_props"] == self.drf_metadata

    def test_retrieve_capture_404(self) -> None:
        """Test retrieving a non-existent capture."""
        response = self.client.get(
            self.detail_url("00000000-0000-0000-0000-000000000000"),
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_not_owned_capture_404(self) -> None:
        """Test retrieving a capture owned by another user."""
        other_user = User.objects.create(
            email="other@test.com",
            password="test-pass-123",  # noqa: S106
        )
        other_capture = Capture.objects.create(
            owner=other_user,
            capture_type=CaptureType.DigitalRF,
        )

        response = self.client.get(self.detail_url(other_capture.uuid))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_capture_204(self) -> None:
        """Test deleting a capture returns 204."""
        response = self.client.delete(self.detail_url(self.drf_capture.uuid))
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
