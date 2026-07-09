"""Management command to initialize federation sync server token."""

from django.core.management.base import BaseCommand
from loguru import logger as log

from sds_gateway.users.backend_service_key_utils import (
    update_federation_sync_server_token,
)


class Command(BaseCommand):
    help = "Initialize or update the federation sync server authentication token"

    def handle(self, *args, **options) -> None:
        """Initialize the federation sync server token."""
        log.info("Initializing federation sync server token...")

        try:
            update_federation_sync_server_token()
            log.success("Federation sync server token initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize federation sync server token: {e}")
            raise
