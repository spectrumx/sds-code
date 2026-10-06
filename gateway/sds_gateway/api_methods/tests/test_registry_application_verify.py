from __future__ import annotations

from unittest.mock import patch

import pytest
from django.utils import timezone

from sds_gateway.api_methods.federation.registry_application_verify import (
    verify_registry_application,
)
from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus


@pytest.mark.django_db
def test_verify_registry_application_success(user) -> None:
    raw = "test-challenge-token-value"
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token(raw),
        status=RegistryApplicationStatus.PENDING_VERIFICATION.value,
    )
    well_known = {
        "fqdn": "site.example.edu",
        "registry_challenge": raw,
        "gateway_api_base": "https://site.example.edu/api/v1",
        "sync_service_url": "https://site.example.edu/sync",
    }
    with patch(
        "sds_gateway.api_methods.federation.registry_application_verify.fetch_well_known_json",
        return_value=well_known,
    ):
        result = verify_registry_application(application)

    assert result.ok
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.PENDING_APPROVAL.value
    assert application.verified_well_known == well_known
    assert application.gateway_api_base == "https://site.example.edu/api/v1"
    assert application.verification_attempts == 1


@pytest.mark.django_db
def test_verify_registry_application_wrong_challenge(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token("correct"),
        status=RegistryApplicationStatus.PENDING_VERIFICATION.value,
    )
    with patch(
        "sds_gateway.api_methods.federation.registry_application_verify.fetch_well_known_json",
        return_value={"fqdn": "site.example.edu", "registry_challenge": "wrong"},
    ):
        result = verify_registry_application(application)

    assert not result.ok
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.VERIFICATION_FAILED.value
    assert application.last_verification_error


@pytest.mark.django_db
def test_verify_registry_application_expired_challenge(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token("token"),
        status=RegistryApplicationStatus.PENDING_VERIFICATION.value,
        challenge_expires_at=timezone.now() - timezone.timedelta(hours=1),
    )
    result = verify_registry_application(application)
    assert not result.ok
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.PENDING_VERIFICATION.value
    assert application.verification_attempts == 0
