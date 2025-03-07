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
    logging.getLogger("botocore").setLevel(logging.ERROR)
    logging.getLogger("boto3").setLevel(logging.ERROR)
