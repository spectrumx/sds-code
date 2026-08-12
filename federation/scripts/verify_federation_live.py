#!/usr/bin/env python3
"""Smoke-test federation export + search against a running local sync service."""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

HTTP_OK = 200
SYNC_PREFIX = "/sync"


def _normalize_sync_base(url: str) -> str:
    """Ensure sync URLs include the mounted /sync prefix."""
    base = url.rstrip("/")
    if not base.endswith(SYNC_PREFIX):
        base = f"{base}{SYNC_PREFIX}"
    return base


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sync-base",
        default=os.environ.get("FEDERATION_SYNC_URL", "http://localhost:8001"),
    )
    parser.add_argument(
        "--site-fqdn",
        default=os.environ.get("LOCAL_SITE_FQDN", "localhost"),
    )
    parser.add_argument("--q", default="")
    parser.add_argument(
        "--gateway-export",
        default=os.environ.get(
            "GATEWAY_EXPORT_URL",
            "http://localhost:8000/api/v1/federation/export/datasets/",
        ),
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("FEDERATION_GATEWAY_API_KEY", ""),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    base = _normalize_sync_base(args.sync_base)

    with httpx.Client(timeout=30.0) as client:
        health = client.get(f"{base}/health")
        print(f"health {health.status_code}: {health.text[:200]}")
        if health.status_code != HTTP_OK:
            return 1

        headers = {}
        if args.api_key:
            headers["Authorization"] = f"Api-Key: {args.api_key}"
        export = client.get(args.gateway_export, headers=headers)
        print(f"gateway export {export.status_code}")
        if export.status_code == HTTP_OK:
            data = export.json()
            print(f"  export datasets: {len(data)}")
            if data:
                print(f"  first site_name: {data[0].get('site_name')}")

        listed = client.get(
            f"{base}/api/v1/webhook/list-datasets/",
        )
        print(f"listed datasets {listed.status_code}")
        if listed.status_code == HTTP_OK:
            body = listed.json()
            print(json.dumps(body, indent=2)[:1500])
        else:
            print(listed.text, file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
