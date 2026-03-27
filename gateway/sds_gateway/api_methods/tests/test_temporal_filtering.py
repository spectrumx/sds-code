import time

from unittest.mock import patch
from django.db.models import QuerySet
from django.test import TestCase

import sds_gateway.api_methods.helpers.temporal_filtering as temporal_filtering
from sds_gateway.api_methods.tests.factories import CaptureFactory, DRFDataFileFactory, UserFactory


class TemporalFilteringTestCase(TestCase):
    def setUp(self):
        # get unix timestamp for now
        self.now = int(time.time())
        self.file_count = 10
        self.user = UserFactory()
        self.capture = CaptureFactory(owner=self.user, capture_type="drf")

        # Create 5 DRF data files in sequence with 1 second interval
        self.files = [
            DRFDataFileFactory(
                capture=self.capture,
                owner=self.user,
                name=f"rf@{self.now + i}.000.h5",
            )
            for i in range(self.file_count)
        ]

    def _get_test_capture_bounds(self):
        start_sec = int(self.now)
        end_sec = start_sec + 10  # 10 second span
        return start_sec, end_sec

    def test_rf_filename_ms_conversion(self):
        for i in range(10):
            expected_ms = (self.now + i) * 1000
            filename_to_ms = temporal_filtering.drf_rf_filename_to_ms(self.files[i].name)
            assert filename_to_ms is not None
            assert filename_to_ms == expected_ms

            ms_to_filename = temporal_filtering.drf_rf_filename_from_ms(expected_ms)
            assert ms_to_filename is not None
            assert ms_to_filename == self.files[i].name
    
    def test_get_capture_bounds(self):
        start_sec, end_sec = self._get_test_capture_bounds()
        # mock response, opensearch calls are tested in test_opensearch.py
        mock_response = {
            "found": True,
            "_source": {
                "search_props": {
                    "start_time": start_sec,
                    "end_time": end_sec,
                }
            },
        }
        with patch("sds_gateway.api_methods.helpers.temporal_filtering.get_opensearch_client") as m:
            m.return_value.get.return_value = mock_response
            start_time, end_time = temporal_filtering.get_capture_bounds(
                self.capture.capture_type, str(self.capture.uuid)
            )
        assert start_time is not None
        assert end_time is not None
        assert start_time == start_sec
        assert end_time == end_sec
    
    def test_get_file_cadence(self):
        start_sec, end_sec = self._get_test_capture_bounds()
        # mock response, opensearch calls are tested in test_opensearch.py
        mock_response = {
            "found": True,
            "_source": {
                "search_props": {
                    "start_time": start_sec,
                    "end_time": end_sec,
                }
            },
        }
        with patch("sds_gateway.api_methods.helpers.temporal_filtering.get_opensearch_client") as m:
            m.return_value.get.return_value = mock_response
            file_cadence = temporal_filtering.get_file_cadence(
                self.capture.capture_type, self.capture
            )
            
            expected_cadence = max(
                1, int((end_sec - start_sec) * 1000 / self.file_count)
            )
            
            # duration_ms / DRF data file count (get_drf_data_files_stats total_count)
            assert self.capture.get_drf_data_files_stats()["total_count"] == self.file_count
            assert file_cadence == expected_cadence

    def test_file_filtering(self):
        start_ms = 1000
        end_ms = 5000
        # Inclusive range: 1s, 2s, 3s, 4s, 5s -> 5 files
        expected_count = (end_ms - start_ms) // 1000 + 1
        start_sec, end_sec = self._get_test_capture_bounds()
        mock_response = {
            "found": True,
            "_source": {
                "search_props": {
                    "start_time": start_sec,
                    "end_time": end_sec,
                }
            },
        }
        with patch("sds_gateway.api_methods.helpers.temporal_filtering.get_opensearch_client") as m:
            m.return_value.get.return_value = mock_response
            filtered_files = temporal_filtering.filter_capture_data_files_selection_bounds(
                self.capture.capture_type, self.capture, start_ms, end_ms
            )
        assert isinstance(filtered_files, QuerySet)
        assert filtered_files.count() == expected_count
        names = list(filtered_files.values_list("name", flat=True))
        for i in range(expected_count):
            assert names[i] == self.files[1 + i].name
