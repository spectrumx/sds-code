"""Management command to initialize SVI server token."""

from django.core.management.base import BaseCommand

from sds_gateway.users.svi_utils import update_svi_server_token


class Command(BaseCommand):
    help = "Initialize or update the SVI server authentication token"

    def handle(self, *args, **options) -> None:
        """Initialize the SVI server token."""
        self.stdout.write(self.style.SUCCESS("Initializing SVI server token..."))

        try:
            update_svi_server_token()
            self.stdout.write(
                self.style.SUCCESS("Successfully initialized SVI server token")
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Failed to initialize SVI server token: {e}")
            )
            raise
