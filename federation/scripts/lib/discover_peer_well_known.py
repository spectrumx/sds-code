#!/usr/bin/env python3
"""Fetch /.well-known/sds-federation.json and print peer fields for add-peer.sh."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

_WELL_KNOWN_PATH = "/.well-known/sds-federation.json"
_REQUIRED = ("name", "fqdn", "display_name", "gateway_api_base", "sync_service_url")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: discover_peer_well_known.py FQDN", file=sys.stderr)
        return 2

    fqdn = sys.argv[1].strip().lower()
    if not fqdn or "://" in fqdn or "/" in fqdn:
        print("FQDN must be a hostname only", file=sys.stderr)
        return 2

    url = f"https://{fqdn}{_WELL_KNOWN_PATH}"
    request = urllib.request.Request(url, method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        print(f"failed to fetch {url}: {exc.reason}", file=sys.stderr)
        return 1

    try:
        doc = json.loads(body)
    except json.JSONDecodeError as exc:
        print(f"invalid JSON from {url}: {exc}", file=sys.stderr)
        return 1

    if not isinstance(doc, dict):
        print(f"well-known document must be a JSON object", file=sys.stderr)
        return 1

    doc_fqdn = str(doc.get("fqdn", "")).strip().lower()
    if doc_fqdn != fqdn:
        print(
            f"well-known fqdn {doc_fqdn!r} does not match requested {fqdn!r}",
            file=sys.stderr,
        )
        return 1

    for key in _REQUIRED:
        value = doc.get(key)
        if not isinstance(value, str) or not value.strip():
            print(f"missing or empty well-known field: {key}", file=sys.stderr)
            return 1

    # Shell-friendly lines: KEY=value (no spaces in values expected for URLs/names)
    for key in _REQUIRED:
        print(f"{key}={doc[key].strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
