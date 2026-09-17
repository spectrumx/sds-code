"""Unit tests for details modal registry helpers."""

# ruff: noqa: SLF001

from __future__ import annotations

import pytest

from sds_gateway.users.views import details_modal_registry as reg

pytestmark = pytest.mark.django_db


class TestFormatChannelMetadataValue:
    def test_none_returns_na(self) -> None:
        assert reg.format_channel_metadata_value(None) == "N/A"

    def test_bool_and_string_booleans(self) -> None:
        assert reg.format_channel_metadata_value(value=True) == "Yes"
        assert reg.format_channel_metadata_value(value=False) == "No"
        assert reg.format_channel_metadata_value("true") == "Yes"
        assert reg.format_channel_metadata_value("FALSE") == "No"

    def test_plain_string(self) -> None:
        assert reg.format_channel_metadata_value("hello") == "hello"

    def test_timestamp_seconds(self) -> None:
        # 2000-01-01 00:00:00 UTC — field_name="computer_time" → timestamp
        result = reg.format_channel_metadata_value(946684800, "computer_time")
        assert "2000" in result
        assert "UTC" in result

    def test_frequency_mhz(self) -> None:
        # field_name="sample_rate" → frequency formatting
        assert "MHz" in reg.format_channel_metadata_value(2_500_000, "sample_rate")

    def test_frequency_ghz(self) -> None:
        # field_name="center_frequency" → frequency formatting
        assert "GHz" in reg.format_channel_metadata_value(
            2_500_000_000, "center_frequency"
        )

    def test_list_joins(self) -> None:
        assert reg.format_channel_metadata_value([1, 2]) == "1, 2"

    def test_dict_json(self) -> None:
        out = reg.format_channel_metadata_value({"a": 1})
        assert '"a": 1' in out or '"a":1' in out.replace(" ", "")


class TestBuildChannelMetadataRows:
    def test_skips_none_values(self) -> None:
        rows = reg.build_channel_metadata_rows({"keep": "x", "drop": None})
        assert len(rows) == 1
        assert rows[0]["label"] == "Keep"

    def test_empty_metadata(self) -> None:
        assert reg.build_channel_metadata_rows(None) == []
        assert reg.build_channel_metadata_rows({}) == []


class TestCaptureDetailsHelpers:
    def test_capture_details_title_precedence(self) -> None:
        assert reg.capture_details_title({"name": "N"}) == "N"
        assert reg.capture_details_title({"top_level_dir": "/dir"}) == "/dir"
        assert reg.capture_details_title({}) == "Unnamed Capture"

    def test_capture_details_meta_drf(self) -> None:
        meta = reg.capture_details_meta(
            {"capture_type": "drf", "uuid": "u1", "name": "Cap"}
        )
        assert meta["visualize_enabled"] is True
        assert meta["capture_type"] == "drf"
        assert meta["uuid"] == "u1"

    def test_capture_details_meta_non_drf(self) -> None:
        meta = reg.capture_details_meta({"capture_type": "rh"})
        assert meta["visualize_enabled"] is False

    def test_capture_details_meta_drf_peer_disables_visualize(self) -> None:
        meta = reg.capture_details_meta(
            {"capture_type": "drf", "is_federated_peer": True},
        )
        assert meta["visualize_enabled"] is False

    def test_owner_display(self) -> None:
        assert reg._owner_display({"owner": {"email": "a@b.com"}}) == "a@b.com"
        assert reg._owner_display({"owner_name": "Peer Owner"}) == "Peer Owner"
        assert reg._owner_display({}) == "N/A"

    def test_dataset_display(self) -> None:
        assert reg._dataset_display({"datasets": [{"name": "D1"}]}) == "D1"
        assert reg._dataset_display({"dataset": "legacy"}) == "legacy"
        assert reg._dataset_display({}) == "N/A"

    def test_center_frequency_display(self) -> None:
        assert reg._center_frequency_display({"center_frequency_ghz": 2.5}) == (
            "2.500 GHz"
        )
        assert reg._center_frequency_display({"center_frequency_ghz": None}) == "N/A"
        assert (
            reg._center_frequency_display(
                {"search_props": {"center_frequency": 2_500_000_000}},
            )
            == "2.500 GHz"
        )

    def test_channel_summary_single(self) -> None:
        cap = {"is_multi_channel": False, "channel": "ch0"}
        assert reg._channel_summary_label(cap) == "Channel"
        assert reg._channel_summary_value(cap) == "ch0"

    def test_channel_summary_multi(self) -> None:
        cap = {
            "is_multi_channel": True,
            "channels": [{"channel": "a"}, {"channel": "b"}],
        }
        assert reg._channel_summary_label(cap) == "Channels"
        assert reg._channel_summary_value(cap) == "a, b"

    def test_accordion_channels_empty_for_single(self) -> None:
        assert reg._accordion_channels({"is_multi_channel": False}) == []

    def test_accordion_channels_multi(self) -> None:
        cap = {
            "is_multi_channel": True,
            "channels": [
                {"channel": "ch1", "channel_metadata": {"gain": 1}},
            ],
        }
        acc = reg._accordion_channels(cap)
        assert len(acc) == 1
        assert acc[0]["channel_name"] == "ch1"
        assert acc[0]["metadata_rows"]


class TestCaptureFileSummaryFromDict:
    EXPECTED_COUNT = 5
    EXPECTED_SIZE = 1000
    FALLBACK_COUNT = 3
    FALLBACK_SIZE = 500
    EXPECTED_SINGLE_FILE_COUNT = 1
    EXPECTED_SINGLE_FILE_SIZE = 1024

    def test_uses_total_file_fields(self) -> None:
        count, size = reg._capture_file_summary_from_dict(
            {
                "total_file_count": self.EXPECTED_COUNT,
                "total_file_size": self.EXPECTED_SIZE,
            },
        )
        assert count == self.EXPECTED_COUNT
        assert size == self.EXPECTED_SIZE

    def test_falls_back_to_data_files_info(self) -> None:
        count, size = reg._capture_file_summary_from_dict(
            {
                "data_files_info": {
                    "total_count": self.FALLBACK_COUNT,
                    "total_size": self.FALLBACK_SIZE,
                }
            },
        )
        assert count == self.FALLBACK_COUNT
        assert size == self.FALLBACK_SIZE

    def test_falls_back_to_federated_file_count_and_size(self) -> None:
        count, size = reg._capture_file_summary_from_dict(
            {
                "file_count": self.EXPECTED_SINGLE_FILE_COUNT,
                "size": self.EXPECTED_SINGLE_FILE_SIZE,
            },
        )
        assert count == self.EXPECTED_SINGLE_FILE_COUNT
        assert size == self.EXPECTED_SINGLE_FILE_SIZE


class TestNormalizeFederatedCaptureDetails:
    def test_search_props_center_frequency_and_peer_flag(self) -> None:
        out = reg._normalize_federated_capture_details(
            {
                "capture_type": "drf",
                "search_props": {"center_frequency": 1_000_000_000},
            },
        )
        assert out["is_federated_peer"] is True
        assert out["center_frequency_ghz"] == 1.0
        assert reg._center_frequency_display(out) == "1.000 GHz"

    def test_public_dataset_ids_resolved_to_datasets(self, mocker) -> None:
        mocker.patch.object(
            reg,
            "_federated_dataset_names_by_uuid",
            return_value={"ds-uuid": "Peer Dataset"},
        )
        out = reg._normalize_federated_capture_details(
            {"public_dataset_ids": ["ds-uuid"]},
        )
        assert reg._dataset_display(out) == "Peer Dataset"


class TestNormalizeFederatedDatasetDetails:
    EXPECTED_VERSION = 4

    def test_defaults_version_and_parses_updated_at(self) -> None:
        out = reg._normalize_federated_dataset_details(
            {
                "name": "Peer DS",
                "updated_at": "2024-06-01T15:30:00Z",
            },
        )
        assert out["version"] == 1
        assert out["name"] == "Peer DS"
        assert (
            reg._parse_federated_datetime("2024-06-01T15:30:00Z") == out["updated_at"]
        )

    def test_preserves_explicit_version(self) -> None:
        out = reg._normalize_federated_dataset_details(
            {"version": self.EXPECTED_VERSION}
        )
        assert out["version"] == self.EXPECTED_VERSION


class TestFinalizeModalJson:
    def test_finalize_capture_modal_json(self) -> None:
        ctx = {"capture": {"name": "C", "capture_type": "drf", "uuid": "id"}}
        out = reg.finalize_capture_modal_json(ctx, "<p>x</p>")
        assert out["html"] == "<p>x</p>"
        assert out["title"] == "C"
        assert out["meta"]["visualize_enabled"] is True

    def test_finalize_dataset_modal_json_with_version(self) -> None:
        ctx = {"dataset": {"name": "DS", "version": 3, "uuid": "d1"}}
        out = reg.finalize_dataset_modal_json(ctx, "<div/>")
        assert out["title"] == "DS (v3)"
        assert out["meta"]["uuid"] == "d1"

    def test_finalize_dataset_modal_json_without_version(self) -> None:
        ctx = {"dataset": {"name": "DS", "uuid": "d1"}}
        out = reg.finalize_dataset_modal_json(ctx, "")
        assert out["title"] == "DS"


class TestRegistryConsistency:
    def test_registered_asset_types_align(self) -> None:
        types = reg.get_registered_asset_types()
        assert types == frozenset({"capture", "dataset"})
        assert set(reg.DETAILS_MODAL_REGISTRY) == set(types)
        assert set(reg.DETAILS_MODAL_BODY_TEMPLATES) == set(types)
        assert set(reg.DETAILS_MODAL_JSON_BUILDERS) == set(types)
