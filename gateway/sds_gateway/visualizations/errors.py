"""Custom exceptions for the visualizations app."""

from typing import Any


class VisualizationsError(Exception):
    """Base class for all visualizations errors."""

    def __init__(self, message) -> None:
        self.message = message

    def __str__(self) -> Any:
        return self.message


class SourceDataError(VisualizationsError):
    """Exception raised when source data is invalid or missing required information."""


class ConfigurationError(VisualizationsError):
    """Exception raised when processing configuration is invalid or missing."""


class ProcessingError(VisualizationsError):
    """Exception raised when processing fails."""
