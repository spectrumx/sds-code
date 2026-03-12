import os
from socket import gethostname

from loguru import logger as log
from sentry_sdk.types import Event
from sentry_sdk.types import Hint


def _is_staging_guess() -> bool:
    """Determines if the current environment is staging based on hostname."""
    # any of these substrings in hostname or SENTRY_ENVIRONMENT
    # is enough to hint a staging environment
    staging_hints_lower = {
        "staging",
        "-qa",
        ".qa",
    }
    hostname: str = gethostname().lower()
    is_staging_hostname = any(hint in hostname for hint in staging_hints_lower)
    sentry_env = os.getenv("SENTRY_ENVIRONMENT", "").lower()
    is_staging_sentry = any(hint in sentry_env for hint in staging_hints_lower)

    is_staging = is_staging_hostname or is_staging_sentry
    log.debug(f"{is_staging=}")

    return is_staging


def guess_best_sentry_env() -> str:
    return "staging" if _is_staging_guess() else "production"


def before_send(event: Event, hint: Hint) -> Event | None:
    """Before send callback for Sentry."""
    # drop events in test environments
    if is_test_env():
        return None
    # how to add extra data:
    # event["extra"]["foo"] = "bar"    # noqa: ERA001
    return event


def is_test_env() -> bool:
    """Returns whether the current environment is a test environment.

    Useful for:
        + Whether to report errors to Sentry or not.
    """
    env_var = os.getenv("PYTEST_CURRENT_TEST", default=None)
    return env_var is not None


def guess_max_web_download_size() -> int:
    """Determine max web download size based on hostname.

    Returns:
        int: Maximum download size in bytes
            - Production: 20GB
            - Dev/QA (staging): 5GB
    """
    # Production: 20GB, Staging (dev/qa): 5GB
    return (
        20 * 1024 * 1024 * 1024 if not _is_staging_guess() else 5 * 1024 * 1024 * 1024
    )


def guess_admin_console_env(*, is_debug: bool) -> str:
    """Determine the admin console environment label.

    Returns:
        str: One of "production", "staging", or "local".
    """
    if _is_staging_guess():
        return "staging"
    if is_debug:
        return "local"
    # safer default
    return "production"
