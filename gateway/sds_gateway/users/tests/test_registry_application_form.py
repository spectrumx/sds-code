import pytest
from django.contrib.auth import get_user_model

from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus
from sds_gateway.api_methods.models import fqdn_has_open_registry_application
from sds_gateway.users.forms import RegistryApplicationForm

User = get_user_model()
_FORM_TEST_HASH = hash_registry_challenge_token("form-test")


@pytest.mark.django_db
def test_registry_application_form_rejects_open_fqdn(user: User) -> None:
    RegistryApplication.objects.create(
        fqdn="taken.example.edu",
        display_name="Taken Site",
        contact=user,
        challenge_token_hash=_FORM_TEST_HASH,
        status=RegistryApplicationStatus.PENDING_VERIFICATION.value,
    )
    assert fqdn_has_open_registry_application("taken.example.edu")

    form = RegistryApplicationForm(
        data={
            "fqdn": "taken.example.edu",
            "display_name": "Another",
            "proposed_site_name": "another",
        },
    )
    assert not form.is_valid()
    assert "fqdn" in form.errors


@pytest.mark.django_db
def test_registry_application_form_allows_fqdn_after_published(user: User) -> None:
    RegistryApplication.objects.create(
        fqdn="old.example.edu",
        display_name="Old Site",
        contact=user,
        challenge_token_hash=_FORM_TEST_HASH,
        status=RegistryApplicationStatus.PUBLISHED.value,
    )
    assert not fqdn_has_open_registry_application("old.example.edu")

    form = RegistryApplicationForm(
        data={
            "fqdn": "old.example.edu",
            "display_name": "Renewed",
            "proposed_site_name": "renewed",
        },
    )
    assert form.is_valid()
