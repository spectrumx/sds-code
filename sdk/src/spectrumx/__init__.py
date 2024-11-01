"""SpectrumX SDK package."""

# better traceback formatting with rich, if available
try:
    from riches import traceback  # pyright: ignore[reportMissingImports]

    traceback.install()
except ImportError:
    pass

import contextlib
import importlib.metadata

from . import models
from . import utils
from .client import Client

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


def main() -> None:  # pragma: no cover
    """Enables loguru logger when running the module."""
    enable_logging()


def enable_logging() -> None:
    """Enables loguru logger."""
    with contextlib.suppress(NameError):
        log.enable(LIB_NAME)  # pyright: ignore[reportPossiblyUnboundVariable]
        log.info(f"Enabled logging for '{LIB_NAME}'")  # pyright: ignore[reportPossiblyUnboundVariable]


__all__ = [
    "__version__",
    "Client",
    "enable_logging",
    "models",
    "utils",
]

if __name__ == "__main__":  # pragma: no cover
    main()
