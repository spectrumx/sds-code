"""SpectrumX SDK package."""

# ruff: noqa: E402  # imports not at top-level

# -------------------
# better traceback formatting with rich, if available
try:
    from rich import traceback  # pyright: ignore[reportMissingImports]

    traceback.install()
except ImportError:
    pass

# -------------------
# package metadata

import importlib.metadata

from spectrumx.utils import log_user_error

LIB_NAME: str = "spectrumx"

# disables the loguru logger if it is not imported
# TODO: consider using the standard logging module and
#       wrapping it with loguru only when running tests
try:
    from loguru import logger as log

    log.disable(LIB_NAME)
except ImportError:
    pass

__version__ = importlib.metadata.version(LIB_NAME)

# -------------------
# experimental features


class Experiments:
    def enable_capture_search(self) -> None:
        """Enables the experimental capture search feature.

        This feature is experimental and may change or be removed in future versions.
        """
        try:
            from spectrumx.api.captures import (
                _enable_experimental_search,  # pyright: ignore[reportPrivateUsage]
            )

            _enable_experimental_search()
        except ImportError as err:
            log_user_error(
                "Failed to import OpenSearch DSL module. Ensure it is installed."
            )
            msg = "OpenSearch DSL module is required for this feature."
            raise ImportError(msg) from err


experiments = Experiments()

# -------------------
# package imports

from spectrumx import models
from spectrumx.client import Client

# -------------------
# package level functions


def main() -> None:  # pragma: no cover
    """Enables loguru logger when running the module."""
    enable_logging()


def enable_logging() -> None:
    """Enables loguru logger."""
    try:
        log.enable(LIB_NAME)  # pyright: ignore[reportPossiblyUnboundVariable]
        log.info(f"Enabled logging for '{LIB_NAME}'")  # pyright: ignore[reportPossiblyUnboundVariable]
    except NameError:
        import logging

        logger = logging.getLogger(__name__)

        logger.warning("Install Loguru to enable additional spectrumx logging.")


# -------------------
# package exports

__all__ = [
    "Client",
    "__version__",
    "enable_logging",
    "experiments",
    "models",
]

if __name__ == "__main__":  # pragma: no cover
    main()
