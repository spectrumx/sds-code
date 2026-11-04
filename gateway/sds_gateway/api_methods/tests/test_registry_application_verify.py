from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone

from sds_gateway.api_methods.federation.registry_application_verify import (
    verify_registry_application,
)
from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.federation.sync_client import SyncUnavailableError
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus

_SYNC_TEST_URL = "http://sync.test:8000"


@pytest.mark.django_db
@override_settings(
    FEDERATION_SYNC_INTERNAL_URL=_SYNC_TEST_URL,
    FEDERATION_SYNC_ADMIN_TOKEN="admin-token",
)
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
        "sds_gateway.api_methods.federation.registry_application_verify.FederationSyncClient.from_settings",
    ) as mock_factory:
        mock_client = mock_factory.return_value
        mock_client.verify_domain.return_value = {
            "ok": True,
            "well_known": well_known,
        }
        result = verify_registry_application(application)

    assert result.ok
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.PENDING_APPROVAL.value
    assert application.verified_well_known == well_known
    assert application.gateway_api_base == "https://site.example.edu/api/v1"
    assert application.verification_attempts == 1
    mock_client.verify_domain.assert_called_once_with(
        "site.example.edu",
        application.challenge_token_hash,
    )


@pytest.mark.django_db
@override_settings(
    FEDERATION_SYNC_INTERNAL_URL=_SYNC_TEST_URL,
    FEDERATION_SYNC_ADMIN_TOKEN="admin-token",
)
def test_verify_sync_unavailable(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token("token"),
        status=RegistryApplicationStatus.PENDING_VERIFICATION.value,
    )
    with patch(
        "sds_gateway.api_methods.federation.registry_application_verify.FederationSyncClient.from_settings",
        side_effect=SyncUnavailableError("Federation sync is unavailable."),
    ):
        result = verify_registry_application(application)

    assert not result.ok
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.VERIFICATION_FAILED.value
    assert "unavailable" in application.last_verification_error.lower()


@pytest.mark.django_db
@override_settings(
    FEDERATION_SYNC_INTERNAL_URL=_SYNC_TEST_URL,
    FEDERATION_SYNC_ADMIN_TOKEN="admin-token",
)
def test_verify_sync_returns_error(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token("token"),
        status=RegistryApplicationStatus.PENDING_VERIFICATION.value,
    )
    with patch(
        "sds_gateway.api_methods.federation.registry_application_verify.FederationSyncClient.from_settings",
    ) as mock_factory:
        mock_client = mock_factory.return_value
        mock_client.verify_domain.return_value = {
            "ok": False,
            "error": "Could not fetch well-known JSON.",
        }
        result = verify_registry_application(application)

    assert not result.ok
    application.refresh_from_db()
    assert application.last_verification_error == "Could not fetch well-known JSON."


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
