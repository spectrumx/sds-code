import time
from unittest.mock import PropertyMock
from unittest.mock import patch

from django.db.models import QuerySet
from django.test import TestCase

from sds_gateway.api_methods.helpers import temporal_filtering
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.tests.factories import CaptureFactory
from sds_gateway.api_methods.tests.factories import DRFDataFileFactory
from sds_gateway.api_methods.tests.factories import UserFactory


class TemporalFilteringTestCase(TestCase):
    def setUp(self):
        # get unix timestamp for now
        self.now = int(time.time())
        self.file_count = 10
        self.user = UserFactory()
        self.capture = CaptureFactory(owner=self.user, capture_type="drf")

        # DRF data files named rf@<epoch_sec>.000.h5, one per second
        self.files = [
            DRFDataFileFactory(
                capture=self.capture,
                owner=self.user,
                name=f"rf@{self.now + i}.000.h5",
            )
            for i in range(self.file_count)
        ]

    def test_get_capture_files_with_temporal_filter(self):
        start_ms = 1000
        end_ms = 5000
        # Inclusive range: 1s, 2s, 3s, 4s, 5s -> 5 DRF data files
        expected_rf_count = (end_ms - start_ms) // 1000 + 1
        expected_rf_names = {self.files[1 + i].name for i in range(expected_rf_count)}
        # OpenSearch stores bounds as Unix epoch seconds; filenames use the same base.
        # Patch Capture on the helper module so the patched property matches resolution.
        with (
            patch.object(
                temporal_filtering.Capture,
                "start_time",
                new_callable=PropertyMock,
                return_value=self.now,
            ),
            patch.object(
                temporal_filtering.Capture,
                "end_time",
                new_callable=PropertyMock,
                return_value=self.now + 10000,
            ),
        ):
            filtered_files = temporal_filtering.get_capture_files_with_temporal_filter(
                CaptureType(self.capture.capture_type),
                self.capture,
                start_ms,
                end_ms,
            )
        assert isinstance(filtered_files, QuerySet)
        names = list(filtered_files.values_list("name", flat=True))
        rf_names = {n for n in names if n.startswith("rf@")}
        assert len(rf_names) == expected_rf_count
        assert rf_names == expected_rf_names
