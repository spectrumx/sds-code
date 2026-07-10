import logging
import sys

from django.apps import AppConfig
from django.db.models.signals import post_migrate
from loguru import logger as log


def _skip_federation_init_in_ready() -> bool:
    """Management commands that load apps before the schema exists."""
    if len(sys.argv) < 2:  # noqa: PLR2004
        return False
    return sys.argv[1] in {
        "migrate",
        "makemigrations",
        "showmigrations",
        "sqlmigrate",
        "flush",
    }


class ApiMethodsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sds_gateway.api_methods"

    # ignoring imports not at the top level (PLC0415), because it's a common
    #   pattern to import application modules here in ready()
    # ruff: noqa: PLC0415
    def ready(self) -> None:
        import sds_gateway.api_methods.federation.signals
        import sds_gateway.api_methods.schema  # noqa: F401
        from sds_gateway.api_methods.federation.availability import (
            initialize_federation_operational_state,
        )

        def _init_federation_after_migrate(sender, **kwargs) -> None:  # noqa: ARG001
            initialize_federation_operational_state()

        post_migrate.connect(
            _init_federation_after_migrate,
            sender=self,
            dispatch_uid="api_methods_federation_operational_init",
        )

        if not _skip_federation_init_in_ready():
            initialize_federation_operational_state()

        silence_unwanted_logs()


def silence_unwanted_logs() -> None:
    """Usually for modules that are too verbose."""
    log.info("Silencing unwanted logs.")
    log_map: dict[int, list[str]] = {
        logging.ERROR: [
            "boto3",
            "botocore",
        ],
        logging.WARNING: [
            "matplotlib",
            "opensearch",
            "s3transfer",
            "urllib3",
        ],
    }
    for log_level, loggers in log_map.items():
        for logger in loggers:
            logging.getLogger(logger).setLevel(log_level)
            log.trace(f"Silencing {logger} at level {log_level}.")
