"""Internal service auth: DRF Tokens and UserAPIKey mint (SVI, federation sync)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.db import IntegrityError
from rest_framework.authtoken.models import Token

from sds_gateway.api_methods.models import KeySources
from sds_gateway.users.models import User
from sds_gateway.users.models import UserAPIKey

logger = logging.getLogger(__name__)


def get_or_create_service_user(email: str) -> tuple[User, bool]:
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            "is_active": True,
            "is_approved": True,
        },
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
        logger.info("Created service user: %s", email)
    return user, created


def update_service_server_token(*, user_email: str, token_key: str) -> None:
    """Sync DRF authtoken ``Token.key`` for an internal service user."""
    user, _created = get_or_create_service_user(user_email)
    existing = Token.objects.filter(user=user)
    count = existing.count()
    if count:
        existing.delete()
        logger.info("Removed %d token(s) for service user %s", count, user_email)
    Token.objects.create(user=user, key=token_key)
    logger.info("Updated service token for %s", user_email)


def replace_user_api_key_for_source(
    *,
    user: User,
    source: KeySources,
    name: str,
    description: str = "",
) -> str:
    """Delete existing keys for ``(user, source)`` and mint a new Api-Key (SVI pattern)."""
    UserAPIKey.objects.filter(user=user, source=source).delete()
    _obj, raw_key = UserAPIKey.objects.create_key(
        name=name,
        user=user,
        source=source,
        description=description,
    )
    return raw_key


def mint_svi_backend_api_key(user: User) -> str:
    return replace_user_api_key_for_source(
        user=user,
        source=KeySources.SVIBackend,
        name=f"{user.email}-SVI-API-KEY",
    )


def mint_federation_sync_api_key(user: User) -> str:
    return replace_user_api_key_for_source(
        user=user,
        source=KeySources.FederationSync,
        name="federation-sync",
        description="Federation sync service (export endpoints only)",
    )


def update_svi_server_token() -> None:
    """Update the SVI token when ``SVI_SERVER_API_KEY`` changes."""
    try:
        update_service_server_token(
            user_email=settings.SVI_SERVER_EMAIL,
            token_key=settings.SVI_SERVER_API_KEY,
        )
    except (DatabaseError, IntegrityError, ValidationError):
        logger.exception("Failed to update SVI server token")


def update_federation_sync_server_token() -> None:
    """Sync federation-sync DRF Token from ``FEDERATION_SYNC_SERVER_API_KEY``."""
    try:
        update_service_server_token(
            user_email=settings.FEDERATION_SYNC_USER_EMAIL,
            token_key=settings.FEDERATION_SYNC_SERVER_API_KEY,
        )
    except (DatabaseError, IntegrityError, ValidationError):
        logger.exception("Failed to update federation sync server token")
