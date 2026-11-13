from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import override_settings

from sds_gateway.api_methods.federation.registry_application_review import (
    approve_registry_application,
)
from sds_gateway.api_methods.federation.registry_application_review import (
    parse_client_cert_fingerprints,
)
from sds_gateway.api_methods.federation.registry_application_review import (
    reject_registry_application,
)
from sds_gateway.api_methods.federation.registry_application_staff_ops import (
    StaffOpResult,
)
from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus

_REVIEW_HASH_A = hash_registry_challenge_token("review-a")
_REVIEW_HASH_B = hash_registry_challenge_token("review-b")
_REVIEW_HASH_C = hash_registry_challenge_token("review-c")


@pytest.mark.django_db
def test_approve_registry_application_success(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        proposed_site_name="mysite",
        challenge_token_hash=_REVIEW_HASH_A,
        status=RegistryApplicationStatus.PENDING_APPROVAL.value,
        verified_well_known={
            "gateway_api_base": "https://site.example.edu/api/v1",
            "sync_service_url": "https://site.example.edu/sync/",
        },
    )
    staff = user
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])

    result = approve_registry_application(application, staff)

    assert result.ok
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.APPROVED.value
    assert application.site_name == "mysite"
    assert application.reviewed_by == staff
    assert application.reviewed_at is not None
    assert application.gateway_api_base == "https://site.example.edu/api/v1"


@pytest.mark.django_db
def test_approve_registry_application_rejects_duplicate_site_name(user) -> None:
    RegistryApplication.objects.create(
        fqdn="existing.example.edu",
        display_name="Existing",
        contact=user,
        site_name="taken",
        challenge_token_hash=_REVIEW_HASH_B,
        status=RegistryApplicationStatus.APPROVED.value,
    )
    application = RegistryApplication.objects.create(
        fqdn="new.example.edu",
        display_name="New",
        contact=user,
        proposed_site_name="taken",
        challenge_token_hash=_REVIEW_HASH_C,
        status=RegistryApplicationStatus.PENDING_APPROVAL.value,
    )

    result = approve_registry_application(application, user)

    assert not result.ok
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.PENDING_APPROVAL.value


def test_parse_client_cert_fingerprints_comma_separated() -> None:
    assert parse_client_cert_fingerprints("sha256:a, sha256:b") == [
        "sha256:a",
        "sha256:b",
    ]


@pytest.mark.django_db
def test_approve_stores_ca_and_fingerprints(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        proposed_site_name="mysite",
        challenge_token_hash=_REVIEW_HASH_A,
        status=RegistryApplicationStatus.PENDING_APPROVAL.value,
    )
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    result = approve_registry_application(
        application,
        user,
        ca_cert_file="peer-ca.pem",
        client_cert_fingerprints=["sha256:abc"],
    )
    assert result.ok
    application.refresh_from_db()
    assert application.ca_cert_file == "peer-ca.pem"
    assert application.client_cert_fingerprints == ["sha256:abc"]


@pytest.mark.django_db
@override_settings(FEDERATION_REGISTRY_AUTO_PUBLISH_ON_APPROVE=True)
def test_approve_auto_publish_when_enabled(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        proposed_site_name="mysite",
        gateway_api_base="https://site.example.edu/api/v1",
        sync_service_url="https://site.example.edu/sync",
        challenge_token_hash=_REVIEW_HASH_A,
        status=RegistryApplicationStatus.PENDING_APPROVAL.value,
    )
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    with patch(
        "sds_gateway.api_methods.federation.registry_application_review.publish_registry_manifest",
        return_value=StaffOpResult(ok=True, message="Published serial 1."),
    ):
        result = approve_registry_application(application, user)
    assert result.ok
    assert "Published serial 1" in result.message


@pytest.mark.django_db
def test_reject_registry_application(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash=_REVIEW_HASH_A,
        status=RegistryApplicationStatus.PENDING_APPROVAL.value,
    )

    result = reject_registry_application(application, user, reason="Not ready")

    assert result.ok
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.REJECTED.value
    assert application.rejected_reason == "Not ready"
