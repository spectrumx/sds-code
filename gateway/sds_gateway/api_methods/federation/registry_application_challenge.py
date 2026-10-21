"""Applicant challenge reissue and application withdraw for registry intake."""

from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from sds_gateway.api_methods.federation.registry_challenge import (
    generate_registry_challenge_token,
)
from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus
from sds_gateway.api_methods.models import _default_registry_challenge_expires_at

_APPLICANT_MANAGE_STATUSES = frozenset(
    {
        RegistryApplicationStatus.PENDING_VERIFICATION.value,
        RegistryApplicationStatus.VERIFICATION_FAILED.value,
    },
)


@dataclass(frozen=True, slots=True)
class ReissueChallengeResult:
    ok: bool
    message: str
    raw_token: str | None = None


@dataclass(frozen=True, slots=True)
class WithdrawResult:
    ok: bool
    message: str


def applicant_can_manage_challenge(application: RegistryApplication) -> bool:
    return application.status in _APPLICANT_MANAGE_STATUSES


def reissue_registry_challenge(
    application: RegistryApplication,
) -> ReissueChallengeResult:
    if application.status not in _APPLICANT_MANAGE_STATUSES:
        return ReissueChallengeResult(
            ok=False,
            message="A new challenge can only be issued before domain verification succeeds.",
        )

    raw_token = generate_registry_challenge_token()
    application.challenge_token_hash = hash_registry_challenge_token(raw_token)
    application.challenge_expires_at = _default_registry_challenge_expires_at()
    application.status = RegistryApplicationStatus.PENDING_VERIFICATION.value
    application.last_verification_error = ""
    application.save(
        update_fields=[
            "challenge_token_hash",
            "challenge_expires_at",
            "status",
            "last_verification_error",
            "updated_at",
        ],
    )
    return ReissueChallengeResult(
        ok=True,
        message="A new verification token was issued. Copy it now—it is shown only once.",
        raw_token=raw_token,
    )


def withdraw_registry_application(application: RegistryApplication) -> WithdrawResult:
    if application.status not in _APPLICANT_MANAGE_STATUSES:
        return WithdrawResult(
            ok=False,
            message="Only applications awaiting verification can be withdrawn.",
        )

    application.status = RegistryApplicationStatus.WITHDRAWN.value
    application.withdrawn_at = timezone.now()
    application.save(update_fields=["status", "withdrawn_at", "updated_at"])
    return WithdrawResult(
        ok=True,
        message="Application withdrawn. You may submit a new application for this FQDN.",
    )
