#!/usr/bin/env python3
"""Demo the real byte-level progress bars from the SDK.

Creates test files, mocks the gateway HTTP layer to simulate transfers
at a given rate, and runs the real download/upload code paths so you
can see the tqdm bars animate smoothly.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import time
import uuid
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from textwrap import dedent

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
FILE_COUNT = 4
FILE_SIZE = 10_000_000  # 10 MB per file
RATE_MBPS = 1  # 1 MB/s default
MOCK_CHUNK = 256  # tiny internal chunks -> smooth tqdm animation
_MIN_SLEEP_THRESHOLD = 0.001  # 1 ms: minimum sleep the OS scheduler can deliver
_BYTE_KB = 1024  # bytes per kilobyte

# Empirical correction: the time-budget accumulator only accounts for
# sleep duration, not the Python overhead per chunk (byte generation,
# yield, loop, monotonic calls).  In practice the actual throughput ends
# up ~5% higher than the nominal rate, so we discount the rate used for
# timing calculations by this factor to match the target.
_RATE_OVERHEAD_FUDGE = 0.954

# Set dynamically by main() via globals() update; declare here for linting.
rate_bps: float = RATE_MBPS * _BYTE_KB * _BYTE_KB


def _human_bytes(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(value) < _BYTE_KB:
            return f"{value:.1f} {unit}"
        value /= _BYTE_KB
    return f"{value:.1f} PB"


def _human_rate(bps: float) -> str:
    return _human_bytes(int(bps)).replace("B", "B/s")


# ---------------------------------------------------------------------------
# Mock HTTP layer
# ---------------------------------------------------------------------------


class _MockResponse:
    """A requests.Response look-alike that the gateway code accepts."""

    status_code = 200
    ok = True
    reason = "OK"

    def __init__(self, content: bytes, file_size: int | None = None):
        self._content = content
        self._file_size = file_size
        self.headers = {}
        if file_size is not None:
            self.headers["Content-Length"] = str(file_size)

    @property
    def content(self):
        return self._content

    def json(self):
        return json.loads(self._content)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, chunk_size: int = 8192):
        """Yield tiny chunks at the rate, for smooth tqdm updates.

        Instead of calling ``time.sleep`` per chunk (which is
        unreliable for sub-millisecond intervals), we compare cumulative
        expected time against wall clock and only sleep when the deficit
        exceeds 1 ms.  This aggregates many tiny delays into fewer but
        longer sleeps that the OS scheduler can deliver accurately.
        """
        if self._file_size is not None:
            inner = min(chunk_size, MOCK_CHUNK)
            offset = 0
            _t0 = time.monotonic()
            _expected = 0.0
            while offset < self._file_size:
                n = min(inner, self._file_size - offset)
                _expected += n / (rate_bps * _RATE_OVERHEAD_FUDGE)
                _deficit = _expected - (time.monotonic() - _t0)
                if _deficit > _MIN_SLEEP_THRESHOLD:
                    time.sleep(_deficit)
                yield b"\x00" * n
                offset += n
        elif self._content:
            yield self._content


def make_mock_response(content: bytes, *, file_size: int | None = None):
    """Build a requests.Response look-alike that the gateway code accepts."""
    return _MockResponse(content, file_size=file_size)


def make_file_json(i: int, file_uuid: str, size: int, rel: str) -> bytes:
    """Return serialised File JSON that the gateway returns for this file."""
    now = datetime.now(tz=UTC).isoformat()
    later = (datetime.now(tz=UTC) + timedelta(days=30)).isoformat()
    info = {
        "uuid": file_uuid,
        "name": f"demo_file_{i:02d}.bin",
        "media_type": "application/octet-stream",
        "size": size,
        "directory": rel,
        "permissions": "rw-rw-r--",
        "created_at": now,
        "updated_at": now,
        "expiration_date": later,
        "sum_blake3": None,
    }
    return json.dumps(info).encode()


# ---------------------------------------------------------------------------
# Demos
# ---------------------------------------------------------------------------


def demo_downloads(tmp: Path) -> None:
    """Run a full download flow using the real Client code paths.

    The gateway._request is patched so every HTTP call returns a local
    mock response.  All progress bars are the real ones from gateway.py
    and client.py.
    """
    from spectrumx.client import Client
    from spectrumx.gateway import Endpoints
    from spectrumx.gateway import HTTPMethods
    from spectrumx.models.files import File

    os.environ["SPECTRUMX_API_KEY"] = "demo_key"

    client = Client(host="localhost", verbose=True)
    client.dry_run = False
    gateway = client._gateway

    uuids_hex = [uuid.uuid4().hex for _ in range(FILE_COUNT)]
    file_json_map: dict[str, bytes] = {}
    demo_files: list[File] = []
    for i, uid_hex in enumerate(uuids_hex):
        j = make_file_json(i, uid_hex, FILE_SIZE, "/demo")
        file_json_map[uid_hex] = j
        f = File.model_validate_json(j)
        f.size = FILE_SIZE
        f.local_path = tmp / f.name
        demo_files.append(f)

    total_bytes_h = _human_bytes(FILE_COUNT * FILE_SIZE)
    rate_h = _human_rate(rate_bps)
    print(f"  ↓ Downloading {FILE_COUNT} files ({total_bytes_h} at {rate_h})…\n")

    orig_request = gateway._request

    def _mock_request(
        method=None,
        endpoint=None,
        *,
        asset_id=None,
        endpoint_args=None,
        stream=False,
        timeout=None,
        verbose=False,
        **kw,
    ):
        nonlocal orig_request, file_json_map

        if endpoint == Endpoints.FILES and method == HTTPMethods.GET and asset_id:
            uid = asset_id
            if uid in file_json_map:
                return make_mock_response(file_json_map[uid])

        elif endpoint == Endpoints.FILE_DOWNLOAD:
            uid = (endpoint_args or {}).get("uuid") or asset_id
            if uid in file_json_map:
                j = json.loads(file_json_map[uid])
                sz = j.get("size", FILE_SIZE)
                return make_mock_response(b"", file_size=sz)

        return make_mock_response(b'{"detail":"mocked ok"}')

    try:
        gateway._request = _mock_request
        results = client.download(
            files_to_download=demo_files,
            to_local_path=tmp / "downloads",
            verbose=True,
            overwrite=True,
        )
        ok = sum(1 for r in results if r)
        fail = len(results) - ok
        print(f"  ↓ Done: {ok} ok, {fail} failed\n")
    finally:
        gateway._request = orig_request


def demo_uploads(tmp: Path) -> None:
    """Run a real upload flow with the gateway patched to simulate slow I/O.

    The _ProgressFile wrapper in upload_new_file tracks bytes read from the
    source file, which updates the tqdm progress bar.  We patch _request
    so that the FILES endpoint reads from the _ProgressFile (triggering the
    bar) at the configured rate before returning a success response.
    """
    from spectrumx.client import Client
    from spectrumx.gateway import Endpoints

    os.environ["SPECTRUMX_API_KEY"] = "demo_key"
    os.environ.pop("PYTEST_CURRENT_TEST", None)

    client = Client(host="localhost", verbose=True)
    client.dry_run = False
    gateway = client._gateway

    upload_root = tmp / "to_upload"
    upload_root.mkdir(parents=True, exist_ok=True)
    for i in range(FILE_COUNT):
        p = upload_root / f"src_file_{i:02d}.bin"
        sz_left = FILE_SIZE
        with p.open("wb") as f:
            while sz_left:
                n = min(65536, sz_left)
                f.write(os.urandom(n))
                sz_left -= n

    total_h = _human_bytes(FILE_COUNT * FILE_SIZE)
    print(f"  ↑ Uploading {FILE_COUNT} files ({total_h} at {_human_rate(rate_bps)})…\n")

    orig_request = gateway._request

    def _mock_request(
        method=None,
        endpoint=None,
        *,
        asset_id=None,
        endpoint_args=None,
        stream=False,
        timeout=None,
        verbose=False,
        **kw,
    ):
        nonlocal orig_request

        if endpoint == Endpoints.FILE_CONTENTS_CHECK:
            return make_mock_response(
                json.dumps(
                    {
                        "file_exists_in_tree": False,
                        "file_contents_exist_for_user": False,
                        "user_mutable_attributes_differ": False,
                        "asset_id": None,
                    }
                ).encode()
            )
        if endpoint == Endpoints.FILES and kw.get("files"):
            files = kw["files"]
            fp = files.get("file")
            if fp is not None:
                _t0 = time.monotonic()
                _expected = 0.0
                while True:
                    chunk = fp.read(MOCK_CHUNK)
                    if not chunk:
                        break
                    # discounted by _RATE_OVERHEAD_FUDGE (see Config)
                    _expected += len(chunk) / (rate_bps * _RATE_OVERHEAD_FUDGE)
                    _deficit = _expected - (time.monotonic() - _t0)
                    if _deficit > _MIN_SLEEP_THRESHOLD:
                        time.sleep(_deficit)
            return make_mock_response(
                make_file_json(
                    i=0,
                    file_uuid=str(uuid.uuid4()),
                    size=FILE_SIZE,
                    rel="/demo_uploads",
                )
            )
        return make_mock_response(b'{"detail":"mocked"}')

    try:
        gateway._request = _mock_request
        results = client.upload(
            local_path=upload_root,
            sds_path="/demo_uploads",
            verbose=True,
            persist_state=False,
        )
        ok = sum(1 for r in results if r)
        fail = len(results) - ok
        print(f"  ↑ Done: {ok} ok, {fail} failed\n")
    finally:
        gateway._request = orig_request


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

TMP_DIR = Path("/tmp") / f"sdk_demo_progress_{uuid.uuid4().hex[:8]}"


def _cleanup() -> None:
    if TMP_DIR.exists():
        shutil.rmtree(TMP_DIR, ignore_errors=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description=dedent("""\
        Demo real SDK progress bars for byte-level upload/download tracking.

        Creates test files and mocks the gateway HTTP layer so the SDK's
        own tqdm progress bars (in gateway.py, client.py, uploads.py)
        render with realistic timing — no real server needed.
        """)
    )
    parser.add_argument(
        "--demo",
        choices=["download", "upload", "all"],
        default="all",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=RATE_MBPS,
        help=f"Transfer rate in MB/s (default {RATE_MBPS})",
    )
    parser.add_argument(
        "--file-count",
        type=int,
        default=FILE_COUNT,
        help=f"Number of test files (default {FILE_COUNT})",
    )
    args = parser.parse_args()

    globals().update(
        rate_bps=args.rate * 1024 * 1024,
        FILE_COUNT=args.file_count,
    )

    # Clean slate (leftover files from crashed runs confuse the upload scanner)
    _cleanup()
    atexit.register(_cleanup)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    size_h = _human_bytes(FILE_SIZE)
    rate_h = _human_rate(rate_bps)
    print(
        f"\nSDK progress bars demo  |  {args.file_count} files x {size_h} |  {rate_h}\n"
    )

    if args.demo in ("download", "all"):
        print("═" * 56)
        print("  DOWNLOAD — outer progress bar (client.py)")
        print("═" * 56)
        print("  Shows file count with byte postfix per completed file")
        print()
        demo_downloads(TMP_DIR)

    if args.demo in ("upload", "all"):
        print("\n")
        print("═" * 56)
        print("  UPLOAD — workload progress bar (uploads.py)")
        print("═" * 56)
        print("  Shows per-file completion with total bytes transferred")
        print()
        demo_uploads(TMP_DIR)

    print("─" * 56)
    print("  Demo complete. See the SDK code at:\n")
    print("    sdk/src/spectrumx/gateway.py")
    print("    sdk/src/spectrumx/client.py")
    print("    sdk/src/spectrumx/api/uploads.py\n")


if __name__ == "__main__":
    main()
