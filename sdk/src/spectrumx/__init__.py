"""SpectrumX SDK package."""

# ruff: noqa: E402  # imports not at top-level

from tqdm.auto import tqdm

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

    # Remove the default stderr handler that Loguru adds on first import.
    # Add a no-op null handler to prevent Loguru from re-adding the default
    # handler on the first log call. Individual features
    # (enable_logging, enable_structured_logging) add their own sinks
    # as needed.
    log.remove()
    log.add(lambda msg: None, level="TRACE")
except ImportError:
    pass

__version__ = importlib.metadata.version(LIB_NAME)

# -------------------
# experimental features


class Experiments:
    """Methods that enable experimental features."""


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
        # configure loguru to work nicely with tqdm
        _ = log.configure(  # pyright: ignore[reportPossiblyUnboundVariable]
            handlers=[
                {
                    "sink": lambda msg: tqdm.write(msg, end=""),  # pyright: ignore[reportUnknownArgumentType, reportUnknownLambdaType]
                    "colorize": True,
                }
            ]
        )
        from spectrumx.utils import LogCategory  # noqa: PLC0415

        log.bind(cat=LogCategory.CONFIG).info(f"Enabled logging for '{LIB_NAME}'")  # pyright: ignore[reportPossiblyUnboundVariable]
    except NameError:
        import logging  # noqa: PLC0415

        logger = logging.getLogger(__name__)

        logger.warning("Install Loguru to enable additional spectrumx logging.")


# -------------------
# structured logging

from spectrumx.utils import enable_structured_logging

# -------------------
# package exports

__all__ = [
    "Client",
    "__version__",
    "enable_logging",
    "enable_structured_logging",
    "experiments",
    "models",
]

if __name__ == "__main__":  # pragma: no cover
    main()
