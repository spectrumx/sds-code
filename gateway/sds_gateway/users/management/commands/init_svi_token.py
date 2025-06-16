"""Management command to initialize SVI server token."""

from django.core.management.base import BaseCommand
from loguru import logger as log

from sds_gateway.users.svi_utils import update_svi_server_token


class Command(BaseCommand):
    help = "Initialize or update the SVI server authentication token"

    def handle(self, *args, **options) -> None:
        """Initialize the SVI server token."""
        log.info("Initializing SVI server token...")

        try:
            update_svi_server_token()
            log.success("SVI server token initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize SVI server token: {e}")
            raise
