from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core import mail
from django.test import override_settings

from sds_gateway.api_methods.federation.registry_application_applicant_notify import (
    build_published_applicant_context,
    notify_registry_application_published,
    registry_applicant_recipient,
)
from sds_gateway.api_methods.federation.registry_application_verify import (
    apply_verification_result,
    verify_registry_application,
)
from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus

_SYNC_TEST_URL = "http://sync.test:8000"


@pytest.mark.django_db
def test_registry_applicant_recipient_prefers_contact_email(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="peer.example.edu",
        display_name="Peer",
        contact=user,
        contact_email="override@example.com",
        challenge_token_hash=hash_registry_challenge_token("t"),
        status=RegistryApplicationStatus.PUBLISHED.value,
    )
    assert registry_applicant_recipient(application) == "override@example.com"


@pytest.mark.django_db
@override_settings(
    SITE_URL="http://testserver",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@test",
    STATIC_ROOT="",
)
def test_notify_published_task_sends_email(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="peer.example.edu",
        display_name="Peer",
        contact=user,
        contact_email=user.email,
        site_name="peer",
        challenge_token_hash=hash_registry_challenge_token("t"),
        status=RegistryApplicationStatus.PUBLISHED.value,
        published_manifest_serial=7,
    )
    sent = notify_registry_application_published(str(application.pk))
    assert sent == 1
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert user.email in message.to
    assert "peer.example.edu" in message.subject
    assert "7" in message.body


@pytest.mark.django_db
def test_build_published_applicant_context_includes_serial(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="peer.example.edu",
        display_name="Peer",
        contact=user,
        site_name="peer-id",
        challenge_token_hash=hash_registry_challenge_token("t"),
        status=RegistryApplicationStatus.PUBLISHED.value,
        published_manifest_serial=3,
    )
    ctx = build_published_applicant_context(application)
    assert ctx["site_name"] == "peer-id"
    assert ctx["manifest_serial"] == 3


@pytest.mark.django_db
def test_apply_verification_result_does_not_schedule_staff_notify(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token("t"),
        status=RegistryApplicationStatus.PENDING_VERIFICATION.value,
    )
    with patch(
        "sds_gateway.api_methods.federation.registry_application_applicant_notify."
        "schedule_registry_application_applicant_notify",
    ) as mock_schedule:
        apply_verification_result(
            application,
            ok=True,
            message="ok",
            well_known={"fqdn": "site.example.edu"},
        )
    mock_schedule.assert_not_called()


@pytest.mark.django_db
@override_settings(
    FEDERATION_SYNC_INTERNAL_URL=_SYNC_TEST_URL,
    FEDERATION_SYNC_ADMIN_TOKEN="admin-token",
)
def test_verify_success_does_not_schedule_notify(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token("t"),
        status=RegistryApplicationStatus.PENDING_VERIFICATION.value,
    )
    with (
        patch(
            "sds_gateway.api_methods.federation.registry_application_verify."
            "FederationSyncClient.from_settings",
        ) as mock_factory,
        patch(
            "sds_gateway.api_methods.federation.registry_application_applicant_notify."
            "schedule_registry_application_applicant_notify",
        ) as mock_schedule,
    ):
        mock_factory.return_value.verify_domain.return_value = {
            "ok": True,
            "well_known": {"fqdn": "site.example.edu"},
        }
        verify_registry_application(application)
    mock_schedule.assert_not_called()


@pytest.mark.django_db
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
def test_notify_published_skips_when_not_published(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token("t"),
        status=RegistryApplicationStatus.APPROVED.value,
    )
    assert notify_registry_application_published(str(application.pk)) == 0
    assert len(mail.outbox) == 0