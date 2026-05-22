"""Unit tests for details modal registry helpers."""

from __future__ import annotations

import pytest

from sds_gateway.users.views import details_modal_registry as reg

pytestmark = pytest.mark.django_db


class TestFormatChannelMetadataValue:
    def test_none_returns_na(self) -> None:
        assert reg.format_channel_metadata_value(None) == "N/A"

    def test_bool_and_string_booleans(self) -> None:
        assert reg.format_channel_metadata_value(True) == "Yes"
        assert reg.format_channel_metadata_value(False) == "No"
        assert reg.format_channel_metadata_value("true") == "Yes"
        assert reg.format_channel_metadata_value("FALSE") == "No"

    def test_plain_string(self) -> None:
        assert reg.format_channel_metadata_value("hello") == "hello"

    def test_timestamp_seconds(self) -> None:
        # 2000-01-01 00:00:00 UTC
        result = reg.format_channel_metadata_value(946684800, "computer_time")
        assert "2000" in result
        assert "UTC" in result

    def test_frequency_mhz(self) -> None:
        assert "MHz" in reg.format_channel_metadata_value(2_500_000)

    def test_frequency_ghz(self) -> None:
        assert "GHz" in reg.format_channel_metadata_value(2_500_000_000)

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

    def test_owner_display(self) -> None:
        assert reg._owner_display({"owner": {"email": "a@b.com"}}) == "a@b.com"
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


class TestFlattenDatasetTreeToModalRows:
    def test_flattens_files_and_directories(self) -> None:
        tree = {
            "files": [
                {
                    "name": "a.txt",
                    "size": 1024,
                    "created_at": None,
                    "media_type": "text/plain",
                },
            ],
            "children": {
                "sub": {
                    "type": "directory",
                    "name": "sub",
                    "size": 0,
                    "created_at": None,
                    "files": [],
                    "children": {},
                },
            },
        }
        rows = reg.flatten_dataset_tree_to_modal_rows(tree)
        assert len(rows) == 2
        assert rows[0]["name"] == "a.txt"
        assert rows[0]["indent_level"] == 0
        assert rows[0]["has_chevron"] is False
        assert rows[1]["name"] == "sub/"
        assert rows[1]["has_chevron"] is True
        assert rows[1]["icon"] == "bi-folder"

    def test_none_node(self) -> None:
        assert reg.flatten_dataset_tree_to_modal_rows(None) == []


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
