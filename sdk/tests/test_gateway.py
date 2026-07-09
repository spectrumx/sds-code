"""Tests for the gateway module."""

# pyright: reportPrivateUsage=false
# pyright: ignore[reportPrivateUsage]

from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs
from urllib.parse import urlencode

import pytest
import requests
import responses
from loguru import logger as loguru_logger
from pytz import UTC
from spectrumx.errors import AuthError
from spectrumx.errors import FileError
from spectrumx.errors import NetworkError
from spectrumx.gateway import Endpoints
from spectrumx.gateway import GatewayClient
from spectrumx.gateway import HTTPMethods
from spectrumx.gateway import _ProgressFileReader
from spectrumx.models.files import File

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_gateway(**kwargs: Any) -> GatewayClient:
    """Create a GatewayClient with test defaults."""
    defaults: dict[str, Any] = {"host": "localhost", "api_key": "test-api-key"}
    defaults.update(kwargs)
    return GatewayClient(**defaults)


# ---------------------------------------------------------------------------
# existing tests (preserved)
# ---------------------------------------------------------------------------


def test_endpoints() -> None:
    """All endpoints must start with a slash."""
    assert all(
        endpoint.startswith("/") for endpoint in Endpoints.__members__.values()
    ), "All endpoints must start with a slash."


def test_base_url() -> None:
    """The base URL must be properly formatted."""
    gateway = GatewayClient(
        host="fake-host-for-tests.crc.nd.edu",
        api_key="123",
        port=666,
        protocol="sds",
    )
    assert gateway.base_url == "sds://fake-host-for-tests.crc.nd.edu:666"


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_protocol_defaults_http_for_localhost() -> None:
    """Protocol defaults to 'http' when host is 'localhost'."""
    gw = _make_gateway(host="localhost")
    assert gw.protocol == "http"


def test_port_defaults_80_for_http() -> None:
    """Port defaults to 80 when protocol is 'http'."""
    gw = _make_gateway(host="localhost")
    assert gw.port == 80


def test_protocol_defaults_https_for_non_localhost() -> None:
    """Protocol defaults to 'https' when host is not localhost."""
    gw = _make_gateway(host="example.com")
    assert gw.protocol == "https"


def test_port_defaults_443_for_https() -> None:
    """Port defaults to 443 when protocol is 'https'."""
    gw = _make_gateway(host="example.com")
    assert gw.port == 443


def test_session_has_retry_configured() -> None:
    """The requests Session has retry adapters mounted."""
    gw = _make_gateway()
    assert "http://" in gw._session.adapters
    assert "https://" in gw._session.adapters


def test_api_key_is_stored() -> None:
    """_api_key is stored on the instance."""
    gw = _make_gateway(api_key="my-secret-key")
    assert gw._api_key == "my-secret-key"


# ---------------------------------------------------------------------------
# base_url / base_url_no_port
# ---------------------------------------------------------------------------


def test_base_url_no_port() -> None:
    """base_url_no_port returns URL without port."""
    gw = _make_gateway(host="example.com", protocol="https", port=9999)
    assert gw.base_url == "https://example.com:9999"
    assert gw.base_url_no_port == "https://example.com"


# ---------------------------------------------------------------------------
# _headers
# ---------------------------------------------------------------------------


def test_headers_empty_api_key_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """When api_key is empty, log_user_warning is called."""
    caplog.set_level(logging.WARNING)
    gw = _make_gateway(api_key="")
    gw._headers()
    assert "API key not set" in caplog.text


def test_headers_returns_authorization() -> None:
    """_headers returns an Authorization header with Api-Key format."""
    gw = _make_gateway(api_key="my-key")
    headers = gw._headers()
    assert headers == {"Authorization": "Api-Key: my-key"}


# ---------------------------------------------------------------------------
# get_default_payload
# ---------------------------------------------------------------------------


def test_get_default_payload_missing_args_raises_value_error() -> None:
    """When endpoint has missing format args, raises ValueError."""
    gw = _make_gateway()
    with pytest.raises(ValueError, match="missing arguments"):
        gw.get_default_payload(endpoint=Endpoints.FILE_DOWNLOAD)


def test_get_default_payload_includes_asset_id() -> None:
    """When asset_id is provided, URL includes it."""
    gw = _make_gateway()
    asset_uuid = str(uuid.uuid4())
    payload = gw.get_default_payload(endpoint=Endpoints.FILES, asset_id=asset_uuid)
    assert f"/{asset_uuid}/" in payload["url"]


def test_get_default_payload_verify_false_in_test() -> None:
    """verify is False in test environments (is_test_env returns True)."""
    gw = _make_gateway()
    payload = gw.get_default_payload(endpoint=Endpoints.AUTH)
    assert payload["verify"] is False


# ---------------------------------------------------------------------------
# _request
# ---------------------------------------------------------------------------


@pytest.fixture
def loguru_sink() -> Any:
    """Capture loguru records into a list for record-count assertions."""
    records: list[str] = []
    handler_id = loguru_logger.add(records.append, format="{message}", level="DEBUG")
    try:
        yield records
    finally:
        loguru_logger.remove(handler_id)


@responses.activate
def test_request_verbose_sends_request_to_auth_endpoint() -> None:
    """With verbose=True the AUTH request is issued once to the right URL.

    The verbose code path (gateway.py:_request) still executes for coverage; we assert
    on the request outcome (responses.calls) rather than logger internals.
    """
    gw = _make_gateway(verbose=True)
    responses.add(responses.GET, "http://localhost:80/api/v1/auth/", body=b"{}")
    response = gw._request(HTTPMethods.GET, Endpoints.AUTH)
    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == ("http://localhost:80/api/v1/auth/")
    assert responses.calls[0].request.method == "GET"
    assert response.status_code == 200


@responses.activate
def test_request_verbose_with_params_forwards_them_on_the_request() -> None:
    """With verbose=True and params, the params are forwarded on the issued request."""
    gw = _make_gateway(verbose=True)
    responses.add(
        responses.GET,
        "http://localhost:80/api/v1/assets/files/?page=1",
        body=b"{}",
    )
    gw._request(HTTPMethods.GET, Endpoints.FILES, params={"page": 1})
    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == (
        "http://localhost:80/api/v1/assets/files/?page=1"
    )


def test_request_verbose_emits_one_debug_record(loguru_sink: list[str]) -> None:
    """The verbose _request path emits exactly one NETWORK debug record."""
    gw = _make_gateway(verbose=True)
    with responses.RequestsMock() as rsps:
        rsps.add(responses.GET, "http://localhost:80/api/v1/auth/", body=b"{}")
        gw._request(HTTPMethods.GET, Endpoints.AUTH)
    matching = [r for r in loguru_sink if r.startswith("GWY req:")]
    assert len(matching) == 1


def test_request_raises_network_error() -> None:
    """When _session.request raises RequestException, raises NetworkError."""
    gw = _make_gateway()
    with (
        patch.object(
            gw._session,
            "request",
            side_effect=requests.exceptions.ConnectionError("connection refused"),
        ),
        pytest.raises(NetworkError, match="connection refused"),
    ):
        gw._request(HTTPMethods.GET, Endpoints.AUTH)


# ---------------------------------------------------------------------------
# authenticate
# ---------------------------------------------------------------------------


def test_authenticate_no_status_code_raises_auth_error() -> None:
    """When response has no status_code, raises AuthError."""
    gw = _make_gateway()
    resp = requests.Response()
    object.__setattr__(resp, "status_code", None)
    resp._content = b""
    with (
        patch.object(gw._session, "request", return_value=resp),
        pytest.raises(AuthError, match="No response code"),
    ):
        gw.authenticate()


@responses.activate
def test_authenticate_failure_raises_auth_error() -> None:
    """When auth fails (non-200), raises AuthError."""
    gw = _make_gateway()
    responses.add(
        responses.GET,
        "http://localhost:80/api/v1/auth/",
        status=401,
        body=b'{"detail":"Unauthorized"}',
    )
    with pytest.raises(AuthError, match="Authentication failed"):
        gw.authenticate()


@responses.activate
def test_authenticate_success_returns_none() -> None:
    """When auth succeeds, authenticate returns None."""
    gw = _make_gateway()
    responses.add(
        responses.GET,
        "http://localhost:80/api/v1/auth/",
        status=200,
        body=b'{"status":"ok"}',
    )
    result = gw.authenticate()
    assert result is None


# ---------------------------------------------------------------------------
# get_file_contents_by_id
# ---------------------------------------------------------------------------


@responses.activate
def test_get_file_contents_by_id_yields_chunks() -> None:
    """Uses responses to mock streaming download; yields chunks of content."""
    gw = _make_gateway()
    content = b"hello-world-streamed-content"
    responses.add(
        responses.GET,
        "http://localhost:80/api/v1/assets/files/some-uuid/download/",
        body=content,
        status=200,
    )
    chunks = list(gw.get_file_contents_by_id("some-uuid"))
    assert b"".join(chunks) == content


@responses.activate
def test_get_file_contents_by_id_skips_empty_chunks() -> None:
    """Empty chunks yielded by iter_content are skipped."""
    gw = _make_gateway()
    responses.add(
        responses.GET,
        "http://localhost:80/api/v1/assets/files/some-uuid/download/",
        body=b"irrelevant",
        status=200,
    )
    with patch.object(
        requests.Response,
        "iter_content",
        return_value=iter([b"chunk1", b"", b"chunk2"]),
    ):
        chunks = list(gw.get_file_contents_by_id("some-uuid"))
        assert chunks == [b"chunk1", b"chunk2"]


# ---------------------------------------------------------------------------
# update_existing_file_metadata
# ---------------------------------------------------------------------------


@responses.activate
def test_update_existing_file_metadata_sends_put() -> None:
    """Sends PUT request with file metadata and returns response content."""
    gw = _make_gateway()
    file_uuid = uuid.uuid4()
    file_instance = File(
        uuid=file_uuid,
        name="test.txt",
        media_type="text/plain",
        size=100,
        directory=PurePosixPath("/some/dir"),
        permissions="rw-r--r--",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        expiration_date=datetime(2026, 1, 1, tzinfo=UTC),
    )
    responses.add(
        responses.PUT,
        f"http://localhost:80/api/v1/assets/files/{file_uuid.hex}/",
        body=b'{"updated": true}',
        status=200,
    )
    result = gw.update_existing_file_metadata(file_instance)
    assert result == b'{"updated": true}'


def test_update_existing_file_metadata_requires_uuid() -> None:
    """Raises AssertionError when file_instance.uuid is None."""
    gw = _make_gateway()
    file_instance = File(
        uuid=None,
        name="test.txt",
        media_type="text/plain",
        size=100,
        directory=PurePosixPath("/some/dir"),
        permissions="rw-r--r--",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        expiration_date=datetime(2026, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(AssertionError, match="UUID"):
        gw.update_existing_file_metadata(file_instance)


# ---------------------------------------------------------------------------
# get_dataset_files
# ---------------------------------------------------------------------------


@responses.activate
def test_get_dataset_files_with_artifacts_only() -> None:
    """When artifacts_only=True, includes 'artifacts_only' param."""
    gw = _make_gateway()
    ds_uuid = uuid.uuid4()
    params = [("page", 1), ("page_size", 30), ("artifacts_only", "true")]
    url = (
        f"http://localhost:80/api/v1/assets/datasets/{ds_uuid.hex}/files/"
        f"?{urlencode(params)}"
    )
    responses.add(
        responses.GET,
        url,
        body=b'{"files": []}',
        status=200,
    )
    result = gw.get_dataset_files(dataset_uuid=ds_uuid, artifacts_only=True)
    assert result == b'{"files": []}'


# ---------------------------------------------------------------------------
# upload_new_file
# ---------------------------------------------------------------------------


def test_upload_new_file_raises_file_error_when_no_local_path() -> None:
    """When file_instance.local_path is None, raises FileError."""
    gw = _make_gateway()
    file_instance = File(
        name="test.txt",
        media_type="text/plain",
        size=100,
        directory=PurePosixPath("/some/dir"),
        permissions="rw-r--r--",
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        expiration_date=datetime(2026, 1, 1, tzinfo=UTC),
    )
    file_instance.local_path = None
    with pytest.raises(FileError, match="remote file"):
        gw.upload_new_file(file_instance)


# ---------------------------------------------------------------------------
# create_capture
# ---------------------------------------------------------------------------


@responses.activate
def test_create_capture_with_channel_scan_group_name() -> None:
    """create_capture sends channel, scan_group, and name in the JSON payload."""
    gw = _make_gateway()
    responses.add(
        responses.POST,
        "http://localhost:80/api/v1/assets/captures/",
        body=b'{"capture": "created"}',
        status=200,
    )
    result = gw.create_capture(
        top_level_dir="/test/capture",
        capture_type="raw",
        index_name="test_index",
        channel="chan1",
        scan_group="groupA",
        name="my_capture",
    )
    assert result == b'{"capture": "created"}'
    # create_capture sends form-encoded data (requests `data=`), so decode the body
    # and assert structured fields — robust to key naming (avoids "groupA" matching
    # a "scan_group_name" key by accident, which a substring check would do).
    request_body = responses.calls[0].request.body
    assert isinstance(request_body, str | bytes)
    if isinstance(request_body, bytes):
        request_body = request_body.decode()
    body = parse_qs(request_body)
    assert body["channel"] == ["chan1"]
    assert body["scan_group"] == ["groupA"]
    assert body["name"] == ["my_capture"]


# ---------------------------------------------------------------------------
# delete_capture
# ---------------------------------------------------------------------------


@responses.activate
def test_delete_capture_verbose_sends_delete_and_succeeds() -> None:
    """With verbose=True, delete_capture issues DELETE and call completes.

    Asserts request outcome (method + status) instead of logger call counts.
    Keeping verbose=True exercises verbose branches in gateway.py for coverage.
    """
    gw = _make_gateway(verbose=True)
    cap_uuid = uuid.uuid4()
    responses.add(
        responses.DELETE,
        f"http://localhost:80/api/v1/assets/captures/{cap_uuid.hex}/",
        status=204,
    )
    gw.delete_capture(capture_uuid=cap_uuid)
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "DELETE"
    assert responses.calls[0].request.url == (
        f"http://localhost:80/api/v1/assets/captures/{cap_uuid.hex}/"
    )


# ---------------------------------------------------------------------------
# _ProgressFileReader
# ---------------------------------------------------------------------------


def test_progress_file_reader_read_calls_callback() -> None:
    """read() calls callback with length of data."""
    data = b"hello world"
    bio = io.BytesIO(data)
    captured: list[int] = []
    reader = _ProgressFileReader(bio, captured.append)
    result = reader.read()
    assert result == data
    assert captured == [len(data)]


def test_progress_file_reader_getattr_delegates(tmp_path: Path) -> None:
    """__getattr__ delegates to the underlying file object."""
    fp = tmp_path / "test.txt"
    fp.write_text("hello")
    with fp.open("rb") as f:
        reader = _ProgressFileReader(f, lambda n: None)
        assert reader.mode == "rb"
        assert reader.name == str(fp)


def test_progress_file_reader_context_manager(tmp_path: Path) -> None:
    """_ProgressFileReader can be used as a context manager."""
    fp = tmp_path / "test.txt"
    fp.write_text("content")
    f = fp.open("rb")
    reader = _ProgressFileReader(f, lambda n: None)
    with reader as r:
        assert r is reader
    assert f.closed


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


@responses.activate
def test_list_files_with_start_end_time() -> None:
    """list_files includes start_time and end_time params when provided."""
    gw = _make_gateway()
    params = {
        "page": 1,
        "page_size": 30,
        "path": "/test/path",
        "start_time": "2024-01-01T00:00:00Z",
        "end_time": "2024-12-31T23:59:59Z",
    }
    url = "http://localhost:80/api/v1/assets/files/?" + urlencode(params)
    responses.add(
        responses.GET,
        url,
        body=b'{"files": []}',
        status=200,
    )
    result = gw.list_files(
        sds_path="/test/path",
        start_time="2024-01-01T00:00:00Z",
        end_time="2024-12-31T23:59:59Z",
    )
    assert result == b'{"files": []}'
