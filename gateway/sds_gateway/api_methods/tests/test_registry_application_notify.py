from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core import mail
from django.test import override_settings

from sds_gateway.api_methods.federation.registry_application_notify import (
    build_pending_approval_staff_context,
)
from sds_gateway.api_methods.federation.registry_application_notify import (
    build_pending_approval_staff_email,
)
from sds_gateway.api_methods.federation.registry_application_notify import (
    notify_registry_pending_approval_staff,
)
from sds_gateway.api_methods.federation.registry_application_notify import (
    registry_staff_notify_recipients,
)
from sds_gateway.api_methods.federation.registry_application_verify import (
    apply_verification_result,
)
from sds_gateway.api_methods.federation.registry_application_verify import (
    verify_registry_application,
)
from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus

_SYNC_TEST_URL = "http://sync.test:8000"


@pytest.mark.django_db
@override_settings(FEDERATION_REGISTRY_STAFF_NOTIFY_EMAILS=["notify@example.com"])
def test_registry_staff_notify_recipients_uses_setting() -> None:
    assert registry_staff_notify_recipients() == ["notify@example.com"]


@pytest.mark.django_db
@override_settings(
    FEDERATION_REGISTRY_STAFF_NOTIFY_EMAILS=[],
    ADMINS=[("Admin", "fallback@example.com")],
)
def test_registry_staff_notify_recipients_falls_back_to_admins(user) -> None:
    assert registry_staff_notify_recipients() == ["fallback@example.com"]


@pytest.mark.django_db
@override_settings(
    SITE_URL="http://testserver",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    FEDERATION_REGISTRY_STAFF_NOTIFY_EMAILS=["staff@example.com"],
    DEFAULT_FROM_EMAIL="noreply@test",
    STATIC_ROOT="",
)
def test_notify_task_sends_email(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="peer.example.edu",
        display_name="Peer",
        contact=user,
        contact_email=user.email,
        proposed_site_name="peer-id",
        gateway_api_base="https://peer.example.edu/api/v1",
        sync_service_url="https://peer.example.edu/sync",
        challenge_token_hash=hash_registry_challenge_token("t"),
        status=RegistryApplicationStatus.PENDING_APPROVAL.value,
    )
    mailed = notify_registry_pending_approval_staff(str(application.pk))
    assert mailed == 1
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert "peer.example.edu" in message.subject
    assert "peer-id" in message.body
    assert user.email in message.body
    assert "/users/federation/registry/applications/" in message.body


@pytest.mark.django_db
def test_build_pending_approval_staff_email_includes_urls(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="peer.example.edu",
        display_name="Peer",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token("t"),
        status=RegistryApplicationStatus.PENDING_APPROVAL.value,
        verified_well_known={
            "sync_service_url": "https://peer.example.edu/sync",
            "gateway_api_base": "https://peer.example.edu/api/v1",
        },
    )
    ctx = build_pending_approval_staff_context(application)
    assert ctx["sync_service_url"] == "https://peer.example.edu/sync"
    _subject, body = build_pending_approval_staff_email(application)
    assert "https://peer.example.edu/sync" in body


@pytest.mark.django_db
def test_apply_verification_result_schedules_notify_on_transition(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token("t"),
        status=RegistryApplicationStatus.PENDING_VERIFICATION.value,
    )
    with patch(
        "sds_gateway.api_methods.federation.registry_application_verify."
        "schedule_registry_pending_approval_staff_notify",
    ) as mock_schedule:
        apply_verification_result(
            application,
            ok=True,
            message="ok",
            well_known={"fqdn": "site.example.edu"},
        )
    mock_schedule.assert_called_once_with(application.pk)


@pytest.mark.django_db
def test_apply_verification_result_skips_notify_on_failure(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token("t"),
        status=RegistryApplicationStatus.PENDING_VERIFICATION.value,
    )
    with patch(
        "sds_gateway.api_methods.federation.registry_application_verify."
        "schedule_registry_pending_approval_staff_notify",
    ) as mock_schedule:
        apply_verification_result(application, ok=False, message="nope")
    mock_schedule.assert_not_called()


@pytest.mark.django_db
@override_settings(
    FEDERATION_SYNC_INTERNAL_URL=_SYNC_TEST_URL,
    FEDERATION_SYNC_ADMIN_TOKEN="admin-token",
)
def test_verify_success_schedules_notify(user) -> None:
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
            "sds_gateway.api_methods.federation.registry_application_verify."
            "schedule_registry_pending_approval_staff_notify",
        ) as mock_schedule,
    ):
        mock_factory.return_value.verify_domain.return_value = {
            "ok": True,
            "well_known": {"fqdn": "site.example.edu"},
        }
        verify_registry_application(application)
    mock_schedule.assert_called_once_with(application.pk)


@pytest.mark.django_db
@override_settings(
    FEDERATION_SYNC_INTERNAL_URL=_SYNC_TEST_URL,
    FEDERATION_SYNC_ADMIN_TOKEN="admin-token",
)
def test_notify_task_skips_when_not_pending_approval(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token("t"),
        status=RegistryApplicationStatus.APPROVED.value,
    )
    assert notify_registry_pending_approval_staff(str(application.pk)) == 0
    assert len(mail.outbox) == 0
