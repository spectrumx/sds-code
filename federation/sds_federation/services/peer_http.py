"""HTTP helpers for peer sync and gateway export calls (optional mTLS verify)."""

from __future__ import annotations

from typing import Any

import httpx

DEFAULT_PEER_HTTP_TIMEOUT = 30.0


def build_peer_http_client(
    *,
    timeout: float = DEFAULT_PEER_HTTP_TIMEOUT,
) -> httpx.AsyncClient:
    """Default async client for peer webhooks and gateway export (no custom CA)."""
    return httpx.AsyncClient(timeout=timeout)


async def peer_request(
    http: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    ca_cert_path: str = "",
    headers: dict[str, str] | None = None,
    json: Any | None = None,
) -> httpx.Response:
    """GET/POST against a peer URL, optionally verifying with ``ca_cert_path``.

    When ``ca_cert_path`` is set, opens a short-lived client with that CA bundle
    so the shared ``http`` client can stay verify=True for non-mTLS lab peers.
    """
    kwargs: dict[str, Any] = {}
    if headers is not None:
        kwargs["headers"] = headers
    if json is not None:
        kwargs["json"] = json

    if ca_cert_path:
        async with httpx.AsyncClient(
            verify=ca_cert_path,
            timeout=http.timeout,
        ) as tls_client:
            return await tls_client.request(method, url, **kwargs)
    return await http.request(method, url, **kwargs)
