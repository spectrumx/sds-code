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


class Result:
    """Either packs a value or an exception.

    Call result() to get the value or raise the exception.
    Truthy (`if result`) when successful, falsy when an exception occurred.
    """

    def __init__(
        self,
        value: Any | None = None,
        exception: Exception | None = None,
    ) -> None:
        if value is None and exception is None:
            msg = "Either value or exception must be provided."
            raise ValueError(msg)
        if value is not None and exception is not None:
            msg = "Only one of value or exception can be provided."
            raise ValueError(msg)
        self.value = value
        self.exception = exception

    def __bool__(self) -> bool:
        return self.exception is None

    def __str__(self) -> str:
        return (
            f"Result(value={self.value})"
            if self
            else f"Result(exception={self.exception})"
        )

    def __repr__(self) -> str:
        return self.__str__()

    def __call__(self) -> Any:
        """Returns the value or raises the exception."""
        if self.exception:
            raise self.exception
        return self.value
