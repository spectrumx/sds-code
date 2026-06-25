#!/usr/bin/env python3
# ruff: noqa: T201, BLE001, E402, C901
"""Diagnose corrupt/unreadable DigitalRF metadata files for captures.

Usage:
    python scripts/diagnose_metadata_files.py <capture_uuid>
    python scripts/diagnose_metadata_files.py <file_uuid> [file_uuid ...]
    python scripts/diagnose_metadata_files.py --file ids.txt

For each File record, fetches the object from MinIO to a temp dir,
inspects with h5py, and reports findings.

The --file mode reads UUIDs from a text file (one UUID per line,
blank lines and lines starting with '#' are ignored).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Ensure the project root is on sys.path so the 'config' package is importable.
# Works whether run from project root (cd /app) or via absolute script path.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

import django

django.setup()

import h5py
from django.conf import settings
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.utils.minio_client import get_minio_client


def inspect_file(minio_client, bucket: str, file_obj: File) -> dict:
    """Download a file from MinIO to a temp dir and inspect it."""
    result = {
        "uuid": str(file_obj.uuid),
        "name": file_obj.name,
        "directory": file_obj.directory,
        "s3_key": file_obj.file.name if file_obj.file else "NONE",
    }
    if not file_obj.file:
        result["error"] = "No file field (S3 key) on File record"
        return result

    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = Path(tmpdir) / file_obj.name
        try:
            minio_client.fget_object(
                bucket_name=bucket,
                object_name=file_obj.file.name,
                file_path=str(local_path),
            )
        except Exception as exc:
            result["error"] = f"MinIO fetch failed: {type(exc).__name__}: {exc}"
            return result

        file_size = local_path.stat().st_size
        result["size_bytes"] = file_size

        if file_size == 0:
            result["status"] = "EMPTY_FILE (0 bytes)"
            return result

        # Try to open with h5py
        try:
            with h5py.File(str(local_path), "r") as f:
                keys = list(f.keys())
                result["hdf5_groups"] = keys
                result["hdf5_group_count"] = len(keys)
                if keys:
                    result["first_key"] = keys[0]
                    result["last_key"] = keys[-1]
                # Check attributes
                attrs = dict(f.attrs)
                result["hdf5_attrs"] = {
                    k: (str(v) if isinstance(v, bytes) else v) for k, v in attrs.items()
                }
                result["status"] = "OK"
        except Exception as exc:
            result["error"] = f"h5py open failed: {type(exc).__name__}: {exc}"
            result["status"] = "CORRUPT_HDF5"
    return result


def _read_ids_from_file(path: str) -> list[str]:
    """Read UUIDs from a file, one per line. Skips blanks and comments."""
    ids: list[str] = []
    with Path(path).open() as fh:
        for raw in fh:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            ids.append(stripped)
    return ids


def _files_for_id(target: str) -> list[File]:
    """Resolve a UUID to File objects: try Capture first, then File."""
    files: list[File] = []

    # Try as capture UUID first
    try:
        capture = Capture.objects.get(uuid=target, is_deleted=False)
        files = list(capture.files.filter(is_deleted=False).order_by("name"))
        print(f"\nCapture: {capture.uuid} ({capture.capture_type}, {capture.name})")
        print(f"Channel: {capture.channel}")
        print(f"Top-level dir: {capture.top_level_dir}")
        print(f"Files connected: {len(files)}")
    except Capture.DoesNotExist:
        pass
    else:
        return files

    # Try as file UUID
    try:
        f = File.objects.get(uuid=target, is_deleted=False)
    except File.DoesNotExist:
        pass
    else:
        return [f]

    print(f"Not found: {target}")
    return files


def _print_results(results: list[dict]) -> None:
    """Print a summary of inspection results."""
    by_status: dict[str, list] = {}
    for r in results:
        status = r.get("status", "UNKNOWN")
        by_status.setdefault(status, []).append(r)

    for status, items in sorted(by_status.items()):
        print(f"\n[{status}] — {len(items)} file(s):")
        for item in items:
            print(f"  {item['name']:40s}  s3_key={item['s3_key']}")
            if "size_bytes" in item:
                print(f"    size={item['size_bytes']} bytes")
            if "error" in item:
                print(f"    ERROR: {item['error']}")
            if "hdf5_groups" in item:
                print(
                    f"    groups={item['hdf5_group_count']},"
                    f" first={item.get('first_key')},"
                    f" last={item.get('last_key')}"
                )
            if "hdf5_attrs" in item:
                for k, v in item["hdf5_attrs"].items():
                    print(f"    attr {k}={v}")

    # Specific checks for dmd_properties.h5
    dmd_props = [r for r in results if "dmd_properties" in r["name"]]
    if not dmd_props:
        print("\n\u26a0\ufe0f  WARNING: No dmd_properties.h5 file found!")
        print("   This is required for DigitalMetadataReader initialization.")

    metadata_files = [r for r in results if r["name"].startswith("metadata@")]
    if metadata_files:
        print(f"\nMetadata data files ({len(metadata_files)}):")
        for r in metadata_files:
            status = r.get("status", "???")
            print(f"  {r['name']}: {status}")


def main() -> None:
    min_cli_args = 2
    file_mode_args = 3

    if len(sys.argv) < min_cli_args:
        print(__doc__)
        sys.exit(1)

    # Collect target IDs
    targets: list[str] = []
    if sys.argv[1] == "--file":
        if len(sys.argv) < file_mode_args:
            print("Error: --file requires a path", file=sys.stderr)
            sys.exit(2)
        targets = _read_ids_from_file(sys.argv[2])
        if not targets:
            print("No IDs found in file.", file=sys.stderr)
            sys.exit(1)
    else:
        targets = sys.argv[1:]

    minio_client = get_minio_client()
    bucket = settings.AWS_STORAGE_BUCKET_NAME
    print(f"Bucket: {bucket}")

    all_results: list[dict] = []
    for target in targets:
        files_to_check = _files_for_id(target)
        if not files_to_check:
            continue

        print(f"Checking {len(files_to_check)} file(s)...")
        print("=" * 60)

        for fobj in files_to_check:
            result = inspect_file(minio_client, bucket, fobj)
            all_results.append(result)

    if not all_results:
        print("No files inspected.")
        sys.exit(1)

    _print_results(all_results)


if __name__ == "__main__":
    main()
