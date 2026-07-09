"""Tests for federation sync DRF token init from shared env."""

from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.authtoken.models import Token

from sds_gateway.users.backend_service_key_utils import update_federation_sync_drf_token
from sds_gateway.users.models import User

pytestmark = pytest.mark.django_db


@override_settings(FEDERATION_SYNC_DRF_TOKEN="a" * 40)
def test_update_federation_sync_drf_token_from_settings() -> None:
    User.objects.filter(email="federation-sync@internal.local").delete()

    update_federation_sync_drf_token()

    user = User.objects.get(email="federation-sync@internal.local")
    assert Token.objects.get(user=user).key == "a" * 40


@override_settings(FEDERATION_SYNC_DRF_TOKEN="")
def test_update_requires_token_length() -> None:
    with pytest.raises(ValueError, match="FEDERATION_SYNC_DRF_TOKEN"):
        update_federation_sync_drf_token()
