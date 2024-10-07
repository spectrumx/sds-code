"""SpectrumX SDK package."""

import importlib.metadata

# better traceback formatting with rich, if available
try:
    from rich import traceback

    traceback.install()
except ImportError:
    pass

__version__ = importlib.metadata.version("spectrumx")

from . import models
from . import utils
from .client import Client

__all__ = [
    "__version__",
    "Client",
    "models",
    "utils",
]
