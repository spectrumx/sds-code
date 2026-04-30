"""Tests for dataset manifest query parsing and path normalization."""

import uuid

import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from sds_gateway.api_methods.utils.dataset_manifest_filters import (
    normalize_top_level_dir_prefix,
)
from sds_gateway.api_methods.utils.dataset_manifest_filters import (
    parse_capture_uuid_query,
)


def test_normalize_top_level_dir_prefix() -> None:
    assert normalize_top_level_dir_prefix("foo/bar") == "/foo/bar"
    assert normalize_top_level_dir_prefix("/foo/bar/") == "/foo/bar"
    assert normalize_top_level_dir_prefix("/") == "/"


def test_parse_capture_uuid_query_accepts_comma_separated() -> None:
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    factory = APIRequestFactory()
    req = factory.get("/x", {"capture": f"{u1},{u2}"})
    drf_request = Request(req)
    parsed = parse_capture_uuid_query(drf_request)
    assert parsed == [u1, u2]


def test_parse_capture_uuid_query_invalid_raises() -> None:
    factory = APIRequestFactory()
    req = factory.get("/x", {"capture": "not-a-uuid"})
    drf_request = Request(req)
    with pytest.raises(ValueError, match="Invalid capture UUID"):
        parse_capture_uuid_query(drf_request)
