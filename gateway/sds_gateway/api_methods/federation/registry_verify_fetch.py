"""SSRF-safe fetch of applicant /.well-known/sds-federation.json for registry verify."""

from __future__ import annotations

import ipaddress
import re
import socket
from typing import Any
from urllib.parse import urlparse

import requests
from django.conf import settings
from loguru import logger

from sds_gateway.api_methods.federation.well_known import _is_local_federation_lab
from sds_gateway.api_methods.federation.well_known import resolve_well_known_fetch_url

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


class RegistryVerifyFetchError(Exception):
    """Verify fetch failed; message is safe to show applicants."""


def _normalized_host(fqdn: str) -> str:
    return fqdn.strip().lower().rstrip(".")


def _is_lab_self_fetch(fqdn: str) -> bool:
    if not _is_local_federation_lab():
        return False
    site_fqdn = str(getattr(settings, "SDS_SITE_FQDN", "") or "").strip().lower()
    return bool(site_fqdn) and _normalized_host(fqdn) == site_fqdn


def validate_applicant_hostname_for_verify(fqdn: str) -> None:
    """Reject private, link-local, and non-public resolved targets."""
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
        return

    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        logger.warning("registry verify DNS lookup failed for {}", host, exc_info=True)
        raise RegistryVerifyFetchError(_COULD_NOT_RESOLVE_HOSTNAME) from None

    if not infos:
        raise RegistryVerifyFetchError(_COULD_NOT_RESOLVE_HOSTNAME)

    for *_, sockaddr in infos:
        addr = ipaddress.ip_address(sockaddr[0])
        if not addr.is_global:
            raise RegistryVerifyFetchError(_APPLICANT_HOSTNAME_NOT_ALLOWED)


def fetch_well_known_json(
    fqdn: str,
    timeout: int = _DEFAULT_FETCH_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """GET applicant well-known JSON (HTTPS; local lab may use internal HTTP)."""
    url = resolve_well_known_fetch_url(fqdn)
    if not _is_lab_self_fetch(fqdn):
        validate_applicant_hostname_for_verify(fqdn)
        parsed = urlparse(url)
        expected_host = _normalized_host(fqdn)
        if (
            parsed.scheme != "https"
            or _normalized_host(parsed.hostname or "") != expected_host
        ):
            raise RegistryVerifyFetchError(_INVALID_VERIFY_FETCH_URL)

    try:
        response = requests.get(
            url,
            timeout=timeout,
            allow_redirects=False,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        content = response.content
        if len(content) > _MAX_RESPONSE_BYTES:
            raise RegistryVerifyFetchError(_WELL_KNOWN_TOO_LARGE)
        payload = response.json()
    except requests.RequestException:
        logger.warning(
            "registry verify HTTP failed fqdn={} url={}",
            fqdn,
            url,
            exc_info=True,
        )
        raise RegistryVerifyFetchError(_COULD_NOT_FETCH_WELL_KNOWN) from None
    except ValueError:
        logger.warning("registry verify JSON parse failed fqdn={}", fqdn, exc_info=True)
        raise RegistryVerifyFetchError(_WELL_KNOWN_INVALID_JSON) from None

    if not isinstance(payload, dict):
        raise RegistryVerifyFetchError(_WELL_KNOWN_NOT_OBJECT)
    return payload
