"""Utilities for managing SVI server authentication."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.db import IntegrityError
from rest_framework.authtoken.models import Token

from sds_gateway.users.models import User

logger = logging.getLogger(__name__)


def update_svi_server_token() -> None:
    """Updates the SVI's token for automatic key rotation if the setting changes."""
    try:
        svi_user, created = User.objects.get_or_create(
            email=settings.SVI_SERVER_EMAIL,
            defaults={
                "is_active": True,
                "is_approved": True,
            },
        )

        if created:
            logger.info("Created SVI server user: %s", settings.SVI_SERVER_EMAIL)

        __delete_svi_user_tokens(svi_user)
        __create_svi_user_token(svi_user)

    except (DatabaseError, IntegrityError, ValidationError):
        logger.exception("Failed to update SVI server token")


def __delete_svi_user_tokens(svi_user: User) -> None:
    """Deletes all existing tokens for the SVI user, revoking existing keys."""
    existing_tokens = Token.objects.filter(user=svi_user)
    token_count = existing_tokens.count()
    if token_count > 0:
        existing_tokens.delete()
        logger.info("Removed %d existing token(s) for SVI server user", token_count)


def __create_svi_user_token(svi_user: User) -> None:
    """Creates a new token for the SVI user following the active setting."""
    Token.objects.create(user=svi_user, key=settings.SVI_SERVER_API_KEY)
    logger.info(
        "Successfully updated SVI server token for %s", settings.SVI_SERVER_EMAIL
    )
