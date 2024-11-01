"""Common test fixtures and utilities for the SDS SDK."""

# better traceback formatting with rich, if available
try:
    from rich import traceback

    traceback.install()
except ImportError:
    pass
