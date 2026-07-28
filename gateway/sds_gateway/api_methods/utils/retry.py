"""Generic retry utilities for management commands and services."""

from __future__ import annotations

import time
from typing import TypeVar

from loguru import logger as log
from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError
from opensearchpy.exceptions import ConnectionTimeout

T = TypeVar("T")


def retry_on_opensearch_error(
    func: callable[..., T],
    *,
    max_retries: int = 10,
    backoff_base: int = 2,
    backoff_cap: int = 30,
) -> T:
    """Retry a callable on OpenSearch connection/timeout errors.

    Args:
        func: Callable to execute (no arguments). Raise to retry.
        max_retries: Maximum number of attempts.
        backoff_base: Base for exponential backoff (seconds).
        backoff_cap: Maximum backoff delay (seconds).

    Returns:
        Result of func on success.

    Raises:
        The last exception from func after max_retries exhausted.
    """
    retryable = (OpenSearchConnectionError, ConnectionTimeout)

    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except retryable as e:
            if attempt == max_retries:
                log.error(
                    f"OpenSearch operation failed after {max_retries} attempts: {e}",
                )
                raise
            wait = min(backoff_base**attempt, backoff_cap)
            log.warning(
                f"OpenSearch operation failed (attempt {attempt}/{max_retries}), "
                f"retrying in {wait}s: {e}",
            )
            time.sleep(wait)

    # Unreachable, but satisfies type checker.
    msg = "retry_on_opensearch_error: unexpected fallthrough"
    raise RuntimeError(msg)
