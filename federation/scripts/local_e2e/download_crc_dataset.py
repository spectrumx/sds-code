#!/usr/bin/env python3
"""Download a public dataset from CRC (or SDS_HOST) for local federation fixtures.

Run from the SDK environment (spectrumx is not a federation dependency):

  cd sdk
  cp ../federation/scripts/local_e2e/env.example ../federation/scripts/local_e2e/.env
  # Edit .env: SDS_SECRET_TOKEN=...

  set -a && source ../federation/scripts/local_e2e/.env && set +a
  uv run python ../federation/scripts/local_e2e/download_crc_dataset.py \\
    --dataset-uuid 50e979bd-8018-415c-8212-c08c3dc98654 \\
    --to ./../federation/data/downloaded_dataset

Or from ``federation/``: ``just local-e2e-env`` then ``just download-crc-dataset <uuid>``.

Use ``--top-level-dir`` to limit to one capture tree (Haystack-style DRF folders).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from uuid import UUID

from spectrumx import Client
from spectrumx.errors import SDSError


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-uuid", required=True)
    parser.add_argument(
        "--to",
        type=Path,
        default=Path("downloaded_dataset"),
        help="Local download root",
    )
    parser.add_argument(
        "--top-level-dir",
        default="",
        help="Optional SDS top_level_dir filter (one capture)",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--skip-contents", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    host = os.environ.get("SDS_HOST", "sds.crc.nd.edu")
    client = Client(host=host)
    client.dry_run = False
    client.authenticate()

    dataset_uuid = UUID(args.dataset_uuid)
    top_level_dirs = [args.top_level_dir] if args.top_level_dir.strip() else None

    print(f"Downloading {dataset_uuid} from {host} -> {args.to.resolve()}")
    try:
        results = client.download_dataset(
            dataset_uuid=dataset_uuid,
            to_local_path=args.to,
            top_level_dirs=top_level_dirs,
            skip_contents=args.skip_contents,
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
