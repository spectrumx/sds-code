"""HTTP client for federation sync internal registry API."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

import requests
from django.conf import settings


class SyncUnavailableError(Exception):
    """Sync internal registry API is unreachable or returned a server error."""


class FederationSyncClient:
    def __init__(
        self,
        base_url: str,
        admin_token: str,
        *,
        verify_timeout: float = 45.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._admin_token = admin_token.strip()
        self._verify_timeout = verify_timeout

    @classmethod
    def from_settings(cls) -> FederationSyncClient:
        base_url = str(
            getattr(settings, "FEDERATION_SYNC_INTERNAL_URL", "") or ""
        ).strip()
        token = str(getattr(settings, "FEDERATION_SYNC_ADMIN_TOKEN", "") or "").strip()
        if not base_url:
            msg = "FEDERATION_SYNC_INTERNAL_URL is not configured"
            raise SyncUnavailableError(msg)
        if not token:
            msg = "FEDERATION_SYNC_ADMIN_TOKEN is not configured"
            raise SyncUnavailableError(msg)
        return cls(base_url, token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._admin_token}",
            "Accept": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            response = requests.request(
                method,
                url,
                headers=self._headers(),
                json=json_body,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            msg = "Federation sync is unavailable."
            raise SyncUnavailableError(msg) from exc
        if response.status_code == HTTPStatus.SERVICE_UNAVAILABLE:
            msg = "Federation sync admin API is not configured."
            raise SyncUnavailableError(msg)
        if response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
            msg = "Federation sync is unavailable."
            raise SyncUnavailableError(msg)
        if response.status_code == HTTPStatus.UNAUTHORIZED:
            msg = "Federation sync rejected the admin token."
            raise SyncUnavailableError(msg)
        try:
            payload = response.json()
        except ValueError as exc:
            msg = "Federation sync returned an invalid response."
            raise SyncUnavailableError(msg) from exc
        if not isinstance(payload, dict):
            msg = "Federation sync returned an invalid response."
            raise SyncUnavailableError(msg)
        if response.status_code >= HTTPStatus.BAD_REQUEST and "ok" not in payload:
            detail = payload.get("detail") or response.text
            raise SyncUnavailableError(str(detail))
        return payload

    def verify_domain(self, fqdn: str, challenge_hash: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/internal/registry/verify",
            timeout=self._verify_timeout,
            json_body={"fqdn": fqdn, "challenge_hash": challenge_hash},
        )
