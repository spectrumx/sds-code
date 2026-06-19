"""Create the federation sync service user and API key."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from loguru import logger as log

from sds_gateway.api_methods.models import KeySources
from sds_gateway.users.models import UserAPIKey


class Command(BaseCommand):
    """Provision federation-sync@internal user and a FederationSync API key."""

    help = "Create federation sync service user and API key (prints raw key once)."

    def handle(self, *args, **options) -> None:
        user_model = get_user_model()
        email = settings.FEDERATION_SYNC_USER_EMAIL

        user, created = user_model.objects.get_or_create(
            email=email,
            defaults={
                "is_active": True,
                "is_approved": True,
            },
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
            log.info("Created federation sync user {}", email)
        else:
            log.info("Using existing federation sync user {}", email)

        UserAPIKey.objects.filter(
            user=user,
            source=KeySources.FederationSync,
        ).delete()

        _obj, raw_key = UserAPIKey.objects.create_key(
            name="federation-sync",
            user=user,
            source=KeySources.FederationSync,
            description="Federation sync service (export endpoints only)",
        )
        self.stdout.write(self.style.SUCCESS(f"Federation sync API key: {raw_key}"))
