#!/usr/bin/env python3
"""Download only drf_properties.h5 files for a dataset (optionally one capture).

  cd sdk
  set -a && source ../federation/scripts/local_e2e/.env && set +a
  uv run python ../federation/scripts/local_e2e/download_drf_properties.py \\
    --dataset-uuid 50e979bd-8018-415c-8212-c08c3dc98654 \\
    --to ../federation/data/downloaded_dataset \\
    --top-level-dir '/files/rherban@nd.edu/CU_conference_NCAR_002_b08a_009f70'
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from uuid import UUID

from spectrumx import Client
from spectrumx.errors import SDSError

PROPS_NAME = "drf_properties.h5"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset-uuid", required=True)
    p.add_argument(
        "--to",
        type=Path,
        default=Path("../federation/data/downloaded_dataset"),
        help="Local root (same as download_crc_dataset --to)",
    )
    p.add_argument(
        "--top-level-dir",
        default="",
        help="Optional capture top_level_dir from list_dataset_captures",
    )
    p.add_argument("--capture-uuid", default="", help="Optional capture UUID filter")
    p.add_argument("--list-only", action="store_true", help="List matches, no download")
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    host = os.environ.get("SDS_HOST", "sds.crc.nd.edu")
    client = Client(host=host)
    client.dry_run = False
    client.authenticate()

    dataset_uuid = UUID(args.dataset_uuid)
    top_level_dirs = [args.top_level_dir] if args.top_level_dir.strip() else None
    capture_uuids = [UUID(args.capture_uuid)] if args.capture_uuid.strip() else None

    # Helpful: show captures if you need the exact top_level_dir
    if not top_level_dirs and not capture_uuids:
        caps = client.list_dataset_captures(dataset_uuid)
        print(f"Captures in dataset ({len(caps)}):")
        for c in caps:
            print(
                f"  uuid={c.get('uuid')}  "
                f"top_level_dir={c.get('top_level_dir')}  "
                f"channels={c.get('channels') or c.get('channel')}"
            )

    files = client.datasets.get_files(
        dataset_uuid,
        capture_uuids=capture_uuids,
        top_level_dirs=top_level_dirs,
    )
    props = [f for f in files if f.name == PROPS_NAME]

    if not props:
        print(
            f"No {PROPS_NAME} in dataset manifest "
            f"(filters: top_level_dir={top_level_dirs}, capture={capture_uuids}).\n"
            "If empty, CRC never indexed that file for this capture — "
            "recreate locally with digital_rf instead.",
            file=sys.stderr,
        )
        return 2

    for f in props:
        print(f"  {f.uuid}  {f.directory}/{f.name}  size={f.size}")

    if args.list_only:
        return 0

    print(f"Downloading {len(props)} file(s) from {host} -> {args.to.resolve()}")
    try:
        results = client.download(
            to_local_path=args.to,
            files_to_download=props,
            overwrite=args.overwrite,
            verbose=True,
        )
    except SDSError as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1

    ok = sum(1 for r in results if r)
    fail = len(results) - ok
    print(f"Done: {ok} ok, {fail} failed")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())