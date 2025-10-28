import logging

from django.apps import AppConfig
from loguru import logger as log


class ApiMethodsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sds_gateway.api_methods"

    # ignoring imports not at the top level (PLC0415), because it's a common
    #   pattern to import application modules here in ready()
    # ruff: noqa: PLC0415
    def ready(self) -> None:
        import sds_gateway.api_methods.schema  # noqa: F401

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
