from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests
from django.utils import timezone
from requests import RequestException

from sds_gateway.api_methods.federation.registry_challenge import (
    verify_registry_challenge_token,
)
from sds_gateway.api_methods.federation.well_known import WELL_KNOWN_SDS_FEDERATION_PATH
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus

_VERIFYABLE_STATUSES = frozenset(
    {
        RegistryApplicationStatus.PENDING_VERIFICATION.value,
        RegistryApplicationStatus.VERIFICATION_FAILED.value,
    },
)

_DEFAULT_FETCH_TIMEOUT_SECONDS = 30
_MAX_ERROR_LENGTH = 2000


@dataclass(frozen=True, slots=True)
class VerifyResult:
    ok: bool
    message: str


def fetch_well_known_json(
    fqdn: str, timeout: int = _DEFAULT_FETCH_TIMEOUT_SECONDS
) -> dict[str, Any]:
    """GET https://{fqdn}/.well-known/sds-federation.json."""
    url = f"https://{fqdn.strip().lower()}{WELL_KNOWN_SDS_FEDERATION_PATH}"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        msg = "well-known response is not a JSON object"
        raise ValueError(msg)
    return payload


def parse_and_match_challenge(payload: dict[str, Any], stored_hash: str) -> bool:
    raw = payload.get("registry_challenge")
    if not isinstance(raw, str):
        return False
    return verify_registry_challenge_token(raw.strip(), stored_hash)


def validate_site_identity(
    payload: dict[str, Any], application: RegistryApplication
) -> bool:
    doc_fqdn = payload.get("fqdn")
    if not isinstance(doc_fqdn, str):
        return False
    return doc_fqdn.strip().lower() == application.fqdn.strip().lower()


def _backfill_urls_from_well_known(
    application: RegistryApplication,
    well_known: dict[str, Any],
) -> list[str]:
    updated: list[str] = []
    for field, key in (
        ("gateway_api_base", "gateway_api_base"),
        ("sync_service_url", "sync_service_url"),
    ):
        if getattr(application, field):
            continue
        value = well_known.get(key)
        if isinstance(value, str) and value.strip():
            setattr(application, field, value.strip())
            updated.append(field)
    return updated


def apply_verification_result(
    application: RegistryApplication,
    *,
    ok: bool,
    message: str,
    well_known: dict[str, Any] | None = None,
) -> VerifyResult:
    update_fields = ["status", "last_verification_error", "verification_attempts"]

    application.verification_attempts += 1
    if ok:
        application.status = RegistryApplicationStatus.PENDING_APPROVAL.value
        application.verified_at = timezone.now()
        application.verified_well_known = well_known
        application.last_verification_error = ""
        update_fields.extend(["verified_at", "verified_well_known"])
        if well_known:
            update_fields.extend(
                _backfill_urls_from_well_known(application, well_known)
            )
    else:
        application.status = RegistryApplicationStatus.VERIFICATION_FAILED.value
        application.last_verification_error = message[:_MAX_ERROR_LENGTH]

    application.save(update_fields=list(dict.fromkeys(update_fields)))
    return VerifyResult(ok=ok, message=message)


def verify_registry_application(application: RegistryApplication) -> VerifyResult:
    if application.status not in _VERIFYABLE_STATUSES:
        return VerifyResult(
            ok=False,
            message="This application cannot be verified in its current status.",
        )

    if application.challenge_expires_at <= timezone.now():
        return VerifyResult(
            ok=False,
            message="The verification challenge has expired. Request a new challenge.",
        )

    fqdn = application.fqdn
    try:
        well_known_json = fetch_well_known_json(fqdn)
    except (RequestException, ValueError, TypeError) as exc:
        return apply_verification_result(
            application,
            ok=False,
            message=f"Could not fetch or parse well-known JSON: {exc}",
        )

    if not parse_and_match_challenge(well_known_json, application.challenge_token_hash):
        return apply_verification_result(
            application,
            ok=False,
            message="registry_challenge is missing or does not match your verification token.",
        )

    if not validate_site_identity(well_known_json, application):
        return apply_verification_result(
            application,
            ok=False,
            message="fqdn in well-known JSON does not match this application.",
        )

    return apply_verification_result(
        application,
        ok=True,
        message="Domain verified. Your application is awaiting admin approval.",
        well_known=well_known_json,
    )
