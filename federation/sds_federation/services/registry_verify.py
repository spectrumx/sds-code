"""SSRF-safe fetch of applicant /.well-known/sds-federation.json for registry verify."""

from __future__ import annotations

import asyncio
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger

from sds_federation.models import FederationConfig
from sds_federation.models import env_bool
from sds_federation.services.well_known import WELL_KNOWN_SDS_FEDERATION_PATH

_DEFAULT_FETCH_TIMEOUT_SECONDS = 30
_MAX_RESPONSE_BYTES = 1_000_000
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))*$",
    re.IGNORECASE,
)

_INVALID_APPLICANT_HOSTNAME = "Invalid applicant hostname."
_APPLICANT_HOSTNAME_NOT_ALLOWED = "Applicant hostname is not allowed."
_COULD_NOT_RESOLVE_HOSTNAME = "Could not resolve applicant hostname."
_INVALID_VERIFY_FETCH_URL = "Invalid verify fetch URL."
_WELL_KNOWN_TOO_LARGE = "Well-known response was too large."
_COULD_NOT_FETCH_WELL_KNOWN = "Could not fetch well-known JSON."
_WELL_KNOWN_INVALID_JSON = "Well-known response was not valid JSON."
_WELL_KNOWN_NOT_OBJECT = "Well-known response was not a JSON object."
_HTTP_SUCCESS_STATUS_MIN = 200
_HTTP_SUCCESS_STATUS_MAX = 299
_NO_PINNED_ADDRESSES = "no pinned addresses to connect"


class RegistryVerifyFetchError(Exception):
    """Verify fetch failed; message is safe to show applicants."""


def _normalized_host(fqdn: str) -> str:
    return fqdn.strip().lower().rstrip(".")


def _local_lab_enabled() -> bool:
    return bool(env_bool("FEDERATION_REGISTRY_LOCAL_LAB"))


def _is_self_site_fetch(fqdn: str, config: FederationConfig) -> bool:
    site_fqdn = _normalized_host(config.site.fqdn)
    if not site_fqdn:
        return False
    if _normalized_host(fqdn) != site_fqdn:
        return False
    if os.environ.get("FEDERATION_REGISTRY_VERIFY_FETCH_BASE", "").strip():
        return True
    return _local_lab_enabled()


def resolve_well_known_fetch_url(fqdn: str, config: FederationConfig) -> str:
    normalized = _normalized_host(fqdn)
    if _is_self_site_fetch(fqdn, config):
        base = (
            os.environ.get("FEDERATION_REGISTRY_VERIFY_FETCH_BASE", "").strip()
            or "http://127.0.0.1:8000"
        )
        return f"{base.rstrip('/')}{WELL_KNOWN_SDS_FEDERATION_PATH}"
    return f"https://{normalized}{WELL_KNOWN_SDS_FEDERATION_PATH}"


def validate_applicant_hostname_for_verify(fqdn: str) -> None:
    """Reject private, link-local, and non-public resolved targets."""
    _resolve_global_addresses_for_verify(fqdn)


def _require_global(address: str) -> str:
    try:
        addr = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        raise RegistryVerifyFetchError(_APPLICANT_HOSTNAME_NOT_ALLOWED) from None
    if not addr.is_global:
        raise RegistryVerifyFetchError(_APPLICANT_HOSTNAME_NOT_ALLOWED)
    return address


def _resolve_global_addresses_for_verify(fqdn: str) -> list[str]:
    host = _normalized_host(fqdn)
    if not host or "%" in host or "/" in host or "@" in host or ":" in host:
        raise RegistryVerifyFetchError(_INVALID_APPLICANT_HOSTNAME)

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        if not _HOSTNAME_RE.fullmatch(host):
            raise RegistryVerifyFetchError(_INVALID_APPLICANT_HOSTNAME) from None
    else:
        if not literal.is_global:
            raise RegistryVerifyFetchError(_APPLICANT_HOSTNAME_NOT_ALLOWED)
        return [str(literal)]

    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        logger.warning("registry verify DNS lookup failed for {}", host, exc_info=True)
        raise RegistryVerifyFetchError(_COULD_NOT_RESOLVE_HOSTNAME) from None

    if not infos:
        raise RegistryVerifyFetchError(_COULD_NOT_RESOLVE_HOSTNAME)

    addresses = [_require_global(str(sockaddr[0])) for *_, sockaddr in infos]
    return list(dict.fromkeys(addresses))


def _pinned_https_request(
    hostname: str,
    pinned_address: str,
    path: str,
    timeout: float,
) -> tuple[int, bytes]:
    """GET over TLS to ``hostname`` while TCP connects to a pre-validated address."""
    conn = http.client.HTTPSConnection(host=hostname, port=443, timeout=timeout)
    raw_sock = socket.create_connection((pinned_address, 443), timeout=timeout)
    try:
        tls_sock = ssl.create_default_context().wrap_socket(
            raw_sock,
            server_hostname=hostname,
        )
        conn.sock = tls_sock
        conn.request("GET", path, headers={"Accept": "application/json"})
        response = conn.getresponse()
        body = _read_response_body_limited(response, _MAX_RESPONSE_BYTES)
        return response.status, body
    finally:
        conn.close()
        raw_sock.close()


def _read_response_body_limited(
    response: http.client.HTTPResponse,
    max_bytes: int,
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(8192)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise RegistryVerifyFetchError(_WELL_KNOWN_TOO_LARGE)
        chunks.append(chunk)
    return b"".join(chunks)


def _pinned_https_get(
    url: str,
    hostname: str,
    pinned_addresses: list[str],
    timeout: int,
) -> bytes:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    last_error: BaseException | None = None
    for pinned in pinned_addresses:
        try:
            response_status, body = _pinned_https_request(
                hostname,
                pinned,
                path,
                float(timeout),
            )
        except RegistryVerifyFetchError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            last_error = exc
        else:
            if (
                response_status < _HTTP_SUCCESS_STATUS_MIN
                or response_status > _HTTP_SUCCESS_STATUS_MAX
            ):
                raise RegistryVerifyFetchError(_COULD_NOT_FETCH_WELL_KNOWN) from None
            return body

    if last_error is not None:
        raise RegistryVerifyFetchError(_COULD_NOT_FETCH_WELL_KNOWN) from last_error
    raise RegistryVerifyFetchError(_COULD_NOT_FETCH_WELL_KNOWN)


def _fetch_well_known_json_sync(
    fqdn: str,
    config: FederationConfig,
    timeout: int = _DEFAULT_FETCH_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    expected_host = _normalized_host(fqdn)
    use_pinned = not _is_self_site_fetch(fqdn, config)
    url = resolve_well_known_fetch_url(fqdn, config)

    try:
        if use_pinned:
            pinned = _resolve_global_addresses_for_verify(fqdn)
            parsed = urlparse(url)
            if (
                parsed.scheme != "https"
                or _normalized_host(parsed.hostname or "") != expected_host
            ):
                raise RegistryVerifyFetchError(_INVALID_VERIFY_FETCH_URL)
            content = _pinned_https_get(url, expected_host, pinned, timeout)
        else:
            response = httpx.get(
                url,
                timeout=timeout,
                follow_redirects=False,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            content = response.content
            if len(content) > _MAX_RESPONSE_BYTES:
                raise RegistryVerifyFetchError(_WELL_KNOWN_TOO_LARGE)
    except httpx.HTTPError as exc:
        logger.warning(
            "registry verify HTTP failed fqdn={} url={}",
            fqdn,
            url,
            exc_info=True,
        )
        raise RegistryVerifyFetchError(_COULD_NOT_FETCH_WELL_KNOWN) from exc
    except (OSError, http.client.HTTPException):
        logger.warning(
            "registry verify HTTP failed fqdn={} url={}",
            fqdn,
            url,
            exc_info=True,
        )
        raise RegistryVerifyFetchError(_COULD_NOT_FETCH_WELL_KNOWN) from None

    try:
        payload = json.loads(content)
    except ValueError:
        logger.warning("registry verify JSON parse failed fqdn={}", fqdn, exc_info=True)
        raise RegistryVerifyFetchError(_WELL_KNOWN_INVALID_JSON) from None
    if not isinstance(payload, dict):
        raise RegistryVerifyFetchError(_WELL_KNOWN_NOT_OBJECT)
    return payload


async def fetch_well_known_json(
    fqdn: str,
    config: FederationConfig,
    fetch_timeout_seconds: int = _DEFAULT_FETCH_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        _fetch_well_known_json_sync,
        fqdn,
        config,
        fetch_timeout_seconds,
    )
