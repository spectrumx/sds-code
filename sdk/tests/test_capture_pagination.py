"""Tests for capture pagination functionality."""

import json
import uuid
from unittest.mock import MagicMock

import pytest
from spectrumx.api.captures import CaptureAPI
from spectrumx.api.captures import _extract_page_from_payload
from spectrumx.models.captures import CaptureType


def test_extract_page_from_payload_with_next():
    """Test _extract_page_from_payload when there's a next page."""
    response_with_next = {
        "count": 100,
        "next": "http://api.example.com/captures?page=2",
        "previous": None,
        "results": [
            {"uuid": "123", "name": "capture1"},
            {"uuid": "456", "name": "capture2"}
        ]
    }
    
    raw_bytes = json.dumps(response_with_next).encode()
    captures_list, has_more = _extract_page_from_payload(raw_bytes)
    
    assert len(captures_list) == 2
    assert has_more is True


def test_extract_page_from_payload_without_next():
    """Test _extract_page_from_payload when there's no next page."""
    response_without_next = {
        "count": 2,
        "next": None,
        "previous": None,
        "results": [
            {"uuid": "789", "name": "capture3"}
        ]
    }
    
    raw_bytes = json.dumps(response_without_next).encode()
    captures_list, has_more = _extract_page_from_payload(raw_bytes)
    
    assert len(captures_list) == 1
    assert has_more is False


def test_extract_page_from_payload_no_next_field():
    """Test _extract_page_from_payload when next field is missing."""
    response_no_next_field = {
        "count": 1,
        "results": [
            {"uuid": "abc", "name": "capture4"}
        ]
    }
    
    raw_bytes = json.dumps(response_no_next_field).encode()
    captures_list, has_more = _extract_page_from_payload(raw_bytes)
    
    assert len(captures_list) == 1
    assert has_more is None


def test_capture_listing_pagination():
    """Test that capture listing correctly handles pagination."""
    mock_gateway = MagicMock()
    capture_api = CaptureAPI(gateway=mock_gateway, dry_run=False, verbose=False)
    
    # Mock responses for multiple pages
    def create_capture_data(name, uuid_str=None):
        return {
            "uuid": uuid_str or str(uuid.uuid4()),
            "capture_type": "drf",
            "name": name,
            "capture_props": {},
            "channel": "test_channel",
            "index_name": "captures-drf",
            "origin": "user",
            "scan_group": None,
            "top_level_dir": f"/{name}",
            "files": [],
            "created_at": "2024-01-01T00:00:00Z"
        }
    
    page1_response = {
        "count": 5,
        "next": "http://api.example.com/captures?page=2",
        "results": [
            create_capture_data("capture1"),
            create_capture_data("capture2"),
        ]
    }
    
    page2_response = {
        "count": 5,
        "next": "http://api.example.com/captures?page=3",
        "results": [
            create_capture_data("capture3"),
        ]
    }
    
    page3_response = {
        "count": 5,
        "next": None,  # No more pages
        "results": [
            create_capture_data("capture4"),
            create_capture_data("capture5"),
        ]
    }
    
    # Set up mock responses for different pages
    def mock_list_captures(capture_type=None, page=1, page_size=30):
        if page == 1:
            return json.dumps(page1_response).encode()
        elif page == 2:
            return json.dumps(page2_response).encode()
        elif page == 3:
            return json.dumps(page3_response).encode()
        else:
            return json.dumps({"count": 5, "next": None, "results": []}).encode()
    
    mock_gateway.list_captures.side_effect = mock_list_captures
    
    # Test listing all captures
    captures = capture_api.listing(capture_type=CaptureType.DigitalRF)
    
    # Verify we got all captures from all pages
    assert len(captures) == 5
    assert [c.name for c in captures] == ["capture1", "capture2", "capture3", "capture4", "capture5"]
    
    # Verify mock was called for each page (3 times)
    assert mock_gateway.list_captures.call_count == 3


def test_capture_listing_single_page():
    """Test that capture listing works correctly with a single page."""
    mock_gateway = MagicMock()
    capture_api = CaptureAPI(gateway=mock_gateway, dry_run=False, verbose=False)
    
    single_page_response = {
        "count": 2,
        "next": None,
        "results": [
            {
                "uuid": str(uuid.uuid4()),
                "capture_type": "drf",
                "name": "single_capture1",
                "capture_props": {},
                "channel": "test_channel",
                "index_name": "captures-drf",
                "origin": "user",
                "scan_group": None,
                "top_level_dir": "/single1",
                "files": [],
                "created_at": "2024-01-01T00:00:00Z"
            },
            {
                "uuid": str(uuid.uuid4()),
                "capture_type": "drf",
                "name": "single_capture2",
                "capture_props": {},
                "channel": "test_channel",
                "index_name": "captures-drf",
                "origin": "user",
                "scan_group": None,
                "top_level_dir": "/single2",
                "files": [],
                "created_at": "2024-01-01T00:00:00Z"
            }
        ]
    }
    
    mock_gateway.list_captures.return_value = json.dumps(single_page_response).encode()
    
    captures = capture_api.listing(capture_type=CaptureType.DigitalRF)
    
    # Should get both captures and only call API once
    assert len(captures) == 2
    assert mock_gateway.list_captures.call_count == 1


def test_capture_listing_empty_results():
    """Test that capture listing works correctly with empty results."""
    mock_gateway = MagicMock()
    capture_api = CaptureAPI(gateway=mock_gateway, dry_run=False, verbose=False)
    
    empty_response = {
        "count": 0,
        "next": None,
        "results": []
    }
    
    mock_gateway.list_captures.return_value = json.dumps(empty_response).encode()
    
    captures = capture_api.listing(capture_type=CaptureType.DigitalRF)
    
    # Should return empty list and only call API once
    assert len(captures) == 0
    assert mock_gateway.list_captures.call_count == 1


def test_capture_listing_dry_run_unaffected():
    """Test that dry run mode still works as expected."""
    mock_gateway = MagicMock()
    capture_api = CaptureAPI(gateway=mock_gateway, dry_run=True, verbose=False)
    
    captures = capture_api.listing(capture_type=CaptureType.DigitalRF)
    
    # Dry run should return simulated captures without calling the API
    assert len(captures) == 3
    assert mock_gateway.list_captures.call_count == 0