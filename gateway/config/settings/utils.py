import os
from socket import gethostname

from sentry_sdk.types import Event
from sentry_sdk.types import Hint


def guess_best_sentry_env() -> str:
    _hostname: str = gethostname()
    _is_staging: bool = "-qa" in _hostname or "-dev" in _hostname
    return "staging" if _is_staging else "production"


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
