"""Tests for federation sync Token + mint endpoint."""

from __future__ import annotations

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from sds_gateway.api_methods.models import KeySources
from sds_gateway.users.backend_service_key_utils import (
    mint_federation_sync_api_key,
    update_federation_sync_server_token,
)
from sds_gateway.users.models import User
from sds_gateway.users.models import UserAPIKey

pytestmark = pytest.mark.django_db


@override_settings(
    FEDERATION_SYNC_USER_EMAIL="federation-sync@internal.local",
    FEDERATION_SYNC_SERVER_API_KEY="a" * 40,
)
class TestFederationSyncMint:
    def setup_method(self) -> None:
        User.objects.filter(email="federation-sync@internal.local").delete()
        update_federation_sync_server_token()

    def test_mint_creates_api_key(self) -> None:
        user = User.objects.get(email="federation-sync@internal.local")
        raw = mint_federation_sync_api_key(user)
        assert raw is not None
        key = UserAPIKey.objects.get_from_key(raw)
        assert key.source == KeySources.FederationSync
        assert key.user_id == user.pk

    def test_mint_replaces_prior_key_like_svi(self) -> None:
        user = User.objects.get(email="federation-sync@internal.local")
        first = mint_federation_sync_api_key(user)
        second = mint_federation_sync_api_key(user)
        assert second != first
        assert (
            UserAPIKey.objects.filter(
                user=user,
                source=KeySources.FederationSync,
            ).count()
            == 1
        )


@override_settings(
    FEDERATION_SYNC_USER_EMAIL="federation-sync@internal.local",
    FEDERATION_SYNC_SERVER_API_KEY="b" * 40,
)
class TestGetFederationSyncApiKeyEndpoint:
    def setup_method(self) -> None:
        User.objects.filter(email="federation-sync@internal.local").delete()
        update_federation_sync_server_token()

    def test_mint_via_http(self) -> None:
        user = User.objects.get(email="federation-sync@internal.local")
        token = Token.objects.get(user=user)
        client = APIClient()
        url = reverse("users:get_federation_sync_api_key")
        response = client.get(
            url,
            {"email": user.email},
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )
        assert response.status_code == status.HTTP_200_OK
        assert "api_key" in response.json()
