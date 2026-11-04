"""Domain verification via federation sync internal API (gateway UI orchestration)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.utils import timezone
from loguru import logger

from sds_gateway.api_methods.federation.registry_application_helpers import (
    VERIFYABLE_STATUSES,
)
from sds_gateway.api_methods.federation.registry_application_helpers import (
    backfill_urls_from_well_known,
)
from sds_gateway.api_methods.federation.sync_client import FederationSyncClient
from sds_gateway.api_methods.federation.sync_client import SyncUnavailableError
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus

_MAX_ERROR_LENGTH = 2000
_SYNC_UNAVAILABLE_MESSAGE = (
    "Domain verification is temporarily unavailable. Please try again later."
)
_VERIFY_SUCCESS_MESSAGE = (
    "Domain verified. Your application is awaiting admin approval."
)
_FQDN_MISMATCH_MESSAGE = "fqdn in well-known JSON does not match this application."
_WELL_KNOWN_NOT_OBJECT_MESSAGE = "Well-known response was not a JSON object."


@dataclass(frozen=True, slots=True)
class VerifyResult:
    ok: bool
    message: str


def validate_site_identity(
    payload: dict[str, Any], application: RegistryApplication
) -> bool:
    doc_fqdn = payload.get("fqdn")
    if not isinstance(doc_fqdn, str):
        return False
    return doc_fqdn.strip().lower() == application.fqdn.strip().lower()


def apply_verification_result(
    application: RegistryApplication,
    *,
    ok: bool,
    message: str,
    well_known: dict[str, Any] | None = None,
) -> VerifyResult:
    update_fields = [
        "status",
        "last_verification_error",
        "verification_attempts",
        "updated_at",
    ]

    application.verification_attempts += 1
    if ok:
        application.status = RegistryApplicationStatus.PENDING_APPROVAL.value
        application.verified_at = timezone.now()
        application.verified_well_known = well_known
        application.last_verification_error = ""
        update_fields.extend(["verified_at", "verified_well_known"])
        if well_known:
            update_fields.extend(backfill_urls_from_well_known(application, well_known))
    else:
        application.status = RegistryApplicationStatus.VERIFICATION_FAILED.value
        application.last_verification_error = message[:_MAX_ERROR_LENGTH]

    application.save(update_fields=list(dict.fromkeys(update_fields)))
    return VerifyResult(ok=ok, message=message)


def _validate_sync_payload(
    payload: dict[str, Any], application: RegistryApplication
) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(well_known, None)`` on success or ``(None, error_message)``."""
    if not payload.get("ok"):
        return None, str(payload.get("error") or "Domain verification failed.")
    well_known = payload.get("well_known")
    if not isinstance(well_known, dict):
        return None, _WELL_KNOWN_NOT_OBJECT_MESSAGE
    if not validate_site_identity(well_known, application):
        return None, _FQDN_MISMATCH_MESSAGE
    return well_known, None


def verify_registry_application(
    application: RegistryApplication,
) -> VerifyResult:
    if application.status not in VERIFYABLE_STATUSES:
        return VerifyResult(
            ok=False,
            message="This application cannot be verified in its current status.",
        )

    if application.challenge_expires_at <= timezone.now():
        msg = (
            "The verification challenge has expired. "
            "Issue a new verification token on the application page."
        )
        return VerifyResult(ok=False, message=msg)

    fqdn = application.fqdn
    try:
        client = FederationSyncClient.from_settings()
        payload = client.verify_domain(fqdn, application.challenge_token_hash)
    except SyncUnavailableError:
        # Infrastructure failure: not the applicant's fault, so keep state
        # unchanged and do not expose internal config details.
        logger.exception("registry verify: federation sync unavailable")
        return VerifyResult(ok=False, message=_SYNC_UNAVAILABLE_MESSAGE)

    well_known_json, error = _validate_sync_payload(payload, application)
    if error:
        return apply_verification_result(application, ok=False, message=error)
    return apply_verification_result(
        application,
        ok=True,
        message=_VERIFY_SUCCESS_MESSAGE,
        well_known=well_known_json,
    )
