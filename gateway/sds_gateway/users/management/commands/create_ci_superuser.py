"""Django management command to create a CI superuser."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from loguru import logger as log


class Command(BaseCommand):
    """Create a superuser for CI environment with predefined credentials.

    Creates a superuser with username 'admin', email 'admin@example.com',
    and password 'ci-admin-pass'. If a superuser already exists, this command
    does nothing.
    """

    help = "Create a CI superuser with default credentials (admin/ci-admin-pass)."

    def handle(self, *args, **options) -> None:
        """Create the CI superuser if no superuser exists."""
        user_model = get_user_model()

        if user_model.objects.filter(is_superuser=True).exists():
            log.warning("Superuser already exists, skipping creation")
            return

        if hasattr(settings, "DJANGO_ADMIN_URL") and settings.DJANGO_ADMIN_URL:
            log.warning(
                "DJANGO_ADMIN_URL is set; skipping CI superuser creation. "
                "Is this a CI environment?"
            )
            return

        email = "admin@example.com"
        password = "ci-admin-pass"  # noqa: S105

        user_model.objects.create_superuser(
            email=email,
            password=password,
        )

        log.success(f"Superuser created for CI: {email} / {password}")
