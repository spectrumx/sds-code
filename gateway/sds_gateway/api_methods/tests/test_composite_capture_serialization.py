"""Tests for composite (multi-channel) capture serialization.

Focused on per-channel metadata: indexed ``channel_metadata`` and OpenSearch-derived
bounds/cadence must stay distinct after ``CompositeCaptureSerializer`` runs, and
top-level summary fields must reflect the envelope across channels.
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.serializers.capture_serializers import (
    CompositeCaptureSerializer,
)
from sds_gateway.api_methods.serializers.capture_serializers import (
    _epoch_sec_to_iso_utc_z,
)
from sds_gateway.api_methods.serializers.capture_serializers import (
    build_composite_capture_data,
)
from sds_gateway.api_methods.views.capture_endpoints import _normalize_top_level_dir

User = get_user_model()


def _two_drf_captures_same_group() -> tuple[Capture, Capture]:
    """Two DRF captures sharing ``top_level_dir`` (multi-channel group)."""
    user = User.objects.create(
        email="composite-ser@example.com",
        password="testpassword",  # noqa: S106
        is_approved=True,
    )
    top = _normalize_top_level_dir("test-composite-serialization-group")
    cap0 = Capture.objects.create(
        capture_type=CaptureType.DigitalRF,
        channel="ch0",
        index_name="captures-test-drf",
        owner=user,
        top_level_dir=top,
    )
    cap1 = Capture.objects.create(
        capture_type=CaptureType.DigitalRF,
        channel="ch1",
        index_name="captures-test-drf",
        owner=user,
        top_level_dir=top,
    )
    return cap0, cap1


class CompositeCaptureSerializationTests(TestCase):
    """Serializer-level tests with OpenSearch and index helpers mocked."""

    def test_distinct_channel_metadata_preserved(self) -> None:
        """Per-channel indexed metadata payloads stay on each channel row."""
        cap0, cap1 = _two_drf_captures_same_group()

        def fake_retrieve(capture: Capture) -> dict:
            return {
                "channel_key": capture.channel,
                "capture_pk": str(capture.uuid),
            }

        with patch(
            "sds_gateway.api_methods.serializers.capture_serializers"
            ".retrieve_indexed_metadata",
            side_effect=fake_retrieve,
        ):
            composite = build_composite_capture_data([cap0, cap1])

        with patch.object(Capture, "get_opensearch_metadata", return_value={}):
            out = CompositeCaptureSerializer(composite, context={}).data

        ch_rows = {row["channel"]: row for row in out["channels"]}
        assert ch_rows["ch0"]["channel_metadata"] == {
            "channel_key": "ch0",
            "capture_pk": str(cap0.uuid),
        }
        assert ch_rows["ch1"]["channel_metadata"] == {
            "channel_key": "ch1",
            "capture_pk": str(cap1.uuid),
        }
        # Ensure we did not collapse to a single shared dict object
        assert (
            ch_rows["ch0"]["channel_metadata"] is not ch_rows["ch1"]["channel_metadata"]
        )

    def test_distinct_opensearch_times_cadence_and_envelope(self) -> None:
        """Per-channel bounds/cadence; top-level uses min start and max end."""
        cap0, cap1 = _two_drf_captures_same_group()

        meta_by_uuid = {
            str(cap0.uuid): {
                "start_time": 1_700_000_000,
                "end_time": 1_700_000_100,
                "file_cadence": 400,
            },
            str(cap1.uuid): {
                "start_time": 1_700_000_050,
                "end_time": 1_700_000_200,
                "file_cadence": 800,
            },
        }

        def opensearch_by_instance(self: Capture) -> dict:
            return dict(meta_by_uuid[str(self.uuid)])

        with patch(
            "sds_gateway.api_methods.serializers.capture_serializers"
            ".retrieve_indexed_metadata",
            return_value={},
        ):
            composite = build_composite_capture_data([cap0, cap1])

        with patch.object(
            Capture,
            "get_opensearch_metadata",
            opensearch_by_instance,
        ):
            out = CompositeCaptureSerializer(composite, context={}).data

        ch_rows = {row["channel"]: row for row in out["channels"]}
        assert ch_rows["ch0"]["capture_start_epoch_sec"] == 1_700_000_000
        assert ch_rows["ch0"]["capture_end_epoch_sec"] == 1_700_000_100
        assert ch_rows["ch0"]["length_of_capture_ms"] == 100_000
        assert ch_rows["ch0"]["file_cadence_ms"] == 400

        assert ch_rows["ch1"]["capture_start_epoch_sec"] == 1_700_000_050
        assert ch_rows["ch1"]["capture_end_epoch_sec"] == 1_700_000_200
        assert ch_rows["ch1"]["length_of_capture_ms"] == 150_000
        assert ch_rows["ch1"]["file_cadence_ms"] == 800

        assert out["capture_start_epoch_sec"] == 1_700_000_000
        # Composite serializer exposes end time via ISO/display, not epoch field
        assert out["capture_end_iso_utc"] == _epoch_sec_to_iso_utc_z(1_700_000_200)
        assert out["length_of_capture_ms"] == 200_000
        assert out["file_cadence_ms"] == 600

    def test_channel_with_incomplete_bounds_excluded_from_envelope(self) -> None:
        """Incomplete channel bounds are excluded from the composite envelope."""
        cap0, cap1 = _two_drf_captures_same_group()

        def opensearch_by_instance(self: Capture) -> dict:
            if self.uuid == cap0.uuid:
                return {
                    "start_time": 1_800_000_000,
                    "end_time": 1_800_000_030,
                    "file_cadence": 100,
                }
            return {
                "start_time": 1_800_000_010,
                "end_time": None,
                "file_cadence": 200,
            }

        with patch(
            "sds_gateway.api_methods.serializers.capture_serializers"
            ".retrieve_indexed_metadata",
            return_value={},
        ):
            composite = build_composite_capture_data([cap0, cap1])

        with patch.object(
            Capture,
            "get_opensearch_metadata",
            opensearch_by_instance,
        ):
            out = CompositeCaptureSerializer(composite, context={}).data

        ch_rows = {row["channel"]: row for row in out["channels"]}
        assert ch_rows["ch0"]["length_of_capture_ms"] == 30_000
        assert ch_rows["ch1"]["capture_end_epoch_sec"] is None
        assert ch_rows["ch1"]["length_of_capture_ms"] is None
        # Envelope from only the complete channel
        assert out["capture_start_epoch_sec"] == 1_800_000_000
        assert out["capture_end_iso_utc"] == _epoch_sec_to_iso_utc_z(1_800_000_030)
        assert out["length_of_capture_ms"] == 30_000
