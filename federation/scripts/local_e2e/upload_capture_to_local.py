#!/usr/bin/env python3
"""Upload a local DigitalRF directory to your local gateway as a new capture.

  cd sdk
  cp ../federation/scripts/local_e2e/env.example ../federation/scripts/local_e2e/.env
  # Edit .env: LOCAL_SDS_SECRET_TOKEN=...

  set -a && source ../federation/scripts/local_e2e/.env && set +a
  uv run python ../federation/scripts/local_e2e/upload_capture_to_local.py \\
    --local-path ../federation/data/downloaded_dataset \\
    --sds-path federation-fixture/starlink-sample

Prints the new capture UUID for publish_for_federation / dataset linking.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from pathlib import PurePosixPath

from spectrumx import Client
from spectrumx.errors import SDSError
from spectrumx.models.captures import CaptureType


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local-path",
        type=Path,
        required=True,
        help="Directory containing DRF/HDF5 files (downloaded tree)",
    )
    parser.add_argument(
        "--sds-path",
        default="federation-fixture/sample",
        help="Virtual path under your SDS user root",
    )
    parser.add_argument("--channel", default="0")
    parser.add_argument("--name", default="Federation local fixture capture")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    host = os.environ.get("LOCAL_SDS_HOST", "localhost:8000")
    host = host.removeprefix("https://").removeprefix("http://")
    env_config: dict[str, str] = {}
    token = os.environ.get("LOCAL_SDS_SECRET_TOKEN") or os.environ.get(
        "SDS_SECRET_TOKEN",
        "",
    )
    if token:
        env_config["SDS_SECRET_TOKEN"] = token

    client = Client(host=host, env_config=env_config or None)
    client.dry_run = False
    client.authenticate()

    if not args.local_path.is_dir():
        print(f"Not a directory: {args.local_path}", file=sys.stderr)
        return 1

    print(f"Uploading {args.local_path} -> {args.sds_path} on {client.host}")
    try:
        capture = client.upload_capture(
            local_path=args.local_path,
            sds_path=PurePosixPath(args.sds_path),
            capture_type=CaptureType.DigitalRF,
            channel=args.channel,
            name=args.name,
            verbose=True,
        )
    except SDSError as exc:
        print(f"Upload failed: {exc}", file=sys.stderr)
        return 1

    if capture is None:
        print("Upload returned no capture", file=sys.stderr)
        return 2

    print(f"Capture UUID: {capture.uuid}")
    print(f"top_level_dir: {capture.top_level_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
