"""Custom exceptions for the SDS SDK."""

from typing import Any


class SDSError(Exception):
    """Base class for all SDS errors."""

    def __init__(self, message) -> None:
        self.message = message

    def __str__(self) -> Any:
        return self.message


class AuthError(SDSError):
    """Issue with user authentication against SDS."""


class NetworkError(SDSError):
    """Issue with the client connection to the SDS service."""


class ServiceError(SDSError):
    """Issue with the SDS service."""


class FileError(SDSError):
    """Issue interacting with a file in SDS."""


class CaptureError(SDSError):
    """Issue interacting with a capture in SDS."""


class DatasetError(SDSError):
    """Issue interacting with a dataset in SDS."""


class ExperimentError(SDSError):
    """Issue interacting with an experiment in SDS."""
