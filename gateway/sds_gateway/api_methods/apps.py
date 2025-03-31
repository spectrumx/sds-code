import logging

from django.apps import AppConfig
from loguru import logger as log


class ApiMethodsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sds_gateway.api_methods"

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
            "opensearch",
            "s3transfer",
            "urllib3",
        ],
    }
    for log_level, loggers in log_map.items():
        for logger in loggers:
            logging.getLogger(logger).setLevel(log_level)
            log.debug(f"Silencing {logger} at level {log_level}.")
