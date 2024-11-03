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
    "__version__",
    "Client",
    "enable_logging",
    "models",
]

if __name__ == "__main__":  # pragma: no cover
    main()
