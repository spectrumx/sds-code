#!/usr/bin/env python3
"""Fetch /.well-known/sds-federation.json and print peer fields for add-peer.sh."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

_WELL_KNOWN_PATH = "/.well-known/sds-federation.json"
_REQUIRED = ("name", "fqdn", "display_name", "gateway_api_base", "sync_service_url")
_ARGC_WITH_FQDN = 2
_EXIT_OK = 0
_EXIT_FAILURE = 1
_EXIT_USAGE = 2


def _fetch_document(fqdn: str) -> tuple[dict | None, str | None]:
    url = f"https://{fqdn}{_WELL_KNOWN_PATH}"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        return None, f"failed to fetch {url}: {exc.reason}"

    try:
        doc = json.loads(body)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON from {url}: {exc}"

    if not isinstance(doc, dict):
        return None, "well-known document must be a JSON object"
    return doc, None


def _validate_document(doc: dict, fqdn: str) -> str | None:
    doc_fqdn = str(doc.get("fqdn", "")).strip().lower()
    if doc_fqdn != fqdn:
        return f"well-known fqdn {doc_fqdn!r} does not match requested {fqdn!r}"
    for key in _REQUIRED:
        value = doc.get(key)
        if not isinstance(value, str) or not value.strip():
            return f"missing or empty well-known field: {key}"
    return None


def main() -> int:
    if len(sys.argv) != _ARGC_WITH_FQDN:
        print("usage: discover_peer_well_known.py FQDN", file=sys.stderr)
        return _EXIT_USAGE

    fqdn = sys.argv[1].strip().lower()
    if not fqdn or "://" in fqdn or "/" in fqdn:
        print("FQDN must be a hostname only", file=sys.stderr)
        return _EXIT_USAGE

    doc, err = _fetch_document(fqdn)
    if err:
        print(err, file=sys.stderr)
        return _EXIT_FAILURE

    assert doc is not None
    validation_err = _validate_document(doc, fqdn)
    if validation_err:
        print(validation_err, file=sys.stderr)
        return _EXIT_FAILURE

    for key in _REQUIRED:
        print(f"{key}={doc[key].strip()}")
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
