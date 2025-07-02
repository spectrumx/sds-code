"""Custom exceptions for the SDS SDK."""

import sys
from collections.abc import Sequence
from typing import Any
from typing import Generic
from typing import TypeVar

from spectrumx.utils import log_user_error

# python 3.10 backport
if sys.version_info < (3, 11):  # noqa: UP036
    from typing_extensions import Self  # noqa: UP035 # Required backport
else:
    from typing import Self

from loguru import logger as log

log.trace("Placeholder log avoid reimporting or resolving unused import warnings.")


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

    def extract_existing_capture_uuid(self) -> str | None:
        """Extract existing capture UUID from error message
        if this is a duplicate capture error.

        Returns:
            The UUID of the existing capture if found, None otherwise.
        """
        error_msg = str(self.message).lower()
        if "drf_unique_channel_and_tld" not in error_msg:
            return None

        try:
            uuid_start = str(self.message).find("another capture: ") + len(
                "another capture: "
            )
            uuid_end = str(self.message).find(" ", uuid_start)
            if uuid_end == -1:
                uuid_end = len(str(self.message))
            return str(self.message)[uuid_start:uuid_end].strip()
        except (ValueError, IndexError):
            return None


class DatasetError(SDSError):
    """Issue interacting with a dataset in SDS."""


class ExperimentError(SDSError):
    """Issue interacting with an experiment in SDS."""


T = TypeVar("T")
UnsetT = TypeVar("UnsetT", bound="Unset")


class Unset:
    """A placeholder for unset values and allow None to be a valid value."""

    _instance: None | Self = None

    def __new__(cls, *args, **kwargs) -> "Unset":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<unset>"

    def __bool__(self) -> bool:
        return False

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Unset)


_unset = Unset()
_unset_alt = Unset()
assert _unset is _unset_alt, "Singleton self-test failed"
assert not _unset, "Unset should be falsy"
del _unset_alt


class Result(Generic[T]):
    """Either packs a value (success) or an exception (failure).

    Useful when running several operations that might
        fail, but you'd like to handle failures later.

    Notice the _constructor_ will raise if any are true:
        1. Both `value` and `exception` are provided.
        2. Neither `value` nor `exception` are provided.
        3. `value` is an instance of `Exception`.
        4. `exception` is not an instance of `Exception`.
        5. `error_info` is provided without an `exception`.
           The opposite is allowed.

    Also, `None` is a valid `value` and will be considered a success.

    ### READING a `Result`

    There are several ways to use it. Assuming `result` is an instance of this class:

    1. By calling: `result()` either returns the value or re-raises the exception.
       You can also call `result.unwrap()` for the same effect.
    2. By checking truthfulness: `bool(result) is True` means success.
       This can be used to filter them:
       `failed_jobs = [result for result in all_jobs if not result]`.
    3. To access the value: `my_val = result.value_or(default_value)`.
    4. Or the exception: `my_exc = result.exception_or(default_exception)`.
    6. When failed, see `result.error_info` to get more information if provided.

    ### CREATING a `Result`

    ```
    def dangerous_fn(asset_id: str) -> int:
        if random.random() < 0.1:
            raise KnownError("Something went wrong")
        return hash(asset_id)

    def wrap_dangerous_fn(asset_id) -> Result[int]:
        try:
            return Result(value=dangerous_fn(asset_id))
        except KnownError as e:
            error_info = {
                "reason": "It happens ...",
                "asset_id": asset_id,
            }
            return Result(exception=e, error_info=error_info)
    ```

    #### These examples will raise

    ```
    Result()                                    # empty result
    Result(value=123, exception=RuntimeError()) # both value and exception
    Result(value=123, error_info={})            # error_info without exception
    Result(exception=123)                       # exception is not an Exception
    Result(value=RuntimeError())                # value is an Exception
    ```

    #### These are valid

    ```
    Result(value=123)                               # success
    Result(value=None)                              # success with None
    Result(exception=RuntimeError())                # simple failure
    Result(exception=RuntimeError(), error_info={}) # failure with extra info

    Result(exception=RuntimeError(), error_info=True)
    # allowed but not recommended (`error_info` is not a dict)
    ```

    > May your results be successful!

    """

    def __init__(
        self,
        *,
        value: T | Unset = _unset,
        exception: Exception | Unset = _unset,
        error_info: dict[str, Any] | None = None,
    ) -> None:
        """Initializes a Result object.

        Args:
            value: The value to pack.
            exception: The exception to pack.
            error_info: Additional information about the error.
        """
        if value is _unset and exception is _unset:  # pragma: no cover
            msg = "Either value or exception must be provided."
            raise ValueError(msg)
        if value is not _unset and exception is not _unset:  # pragma: no cover
            msg = "Only one of value or exception can be provided."
            raise ValueError(msg)
        if exception is not _unset and not isinstance(
            exception, Exception
        ):  # pragma: no cover
            msg = "Exception must be an instance of Exception."
            raise ValueError(msg)
        if exception is _unset and error_info is not None:  # pragma: no cover
            msg = "Error info can only be provided with an exception."
            raise ValueError(msg)
        if value is not _unset and isinstance(value, Exception):
            msg = "Value cannot be an instance of Exception."
            raise ValueError(msg)
        # While we encourage `error_info` being a dict[str, Any], we're deliberately
        # not validating its type here to avoid risking the failure of longer-running
        # scripts for a minor issue. If the reader of `error_info` accepts a different
        # type, they have a chance to handle it.
        self._value: T = value
        self._exception: Exception = exception
        self.error_info: dict[str, Any] = error_info if error_info is not None else {}

    def __bool__(self) -> bool:
        _value_is_set = self._value is not _unset
        _exc_is_set = self._exception is not _unset
        assert _value_is_set != _exc_is_set, "Invalid Result state"
        return _value_is_set and not _exc_is_set

    def __str__(self) -> str:
        return (
            f"Result(value={self._value})"
            if self
            else f"Result(exception={self._exception})"
        )

    def __repr__(self) -> str:
        return self.__str__()

    def __call__(self) -> T:
        """Returns the value or raises the exception."""
        if self:
            return self._value
        raise self._exception

    def value_or(self, default: T) -> T:
        """Returns the wrapped value or a default value when result is an exception."""
        return self._value if self else default

    def exception_or(self, default: Exception | None) -> Exception | None:
        """Returns the wrapped exception or a default one when result is a value."""
        return self._exception if not self else default

    def unwrap(self) -> T:
        """Alias for `self()`. Raises if the result is an exception."""
        return self()


def process_upload_results(
    upload_results: Sequence[Result],  # pyright: ignore[reportMissingTypeArgument]
    *,
    verbose: bool,
    raise_on_error: bool,
) -> bool:
    """Process the results of a batch upload, raising if any has failed.

    Args:
        upload_results:     A sequence of Result objects.
        verbose:            Whether to log errors.
        raise_on_error:     Whether to raise an exception on failure.
    Raises:
        The first SDSError wrapped as upload_results if any upload has failed and
        raise_on_error is True.
    Returns:
        bool: True if all uploads were successful, False otherwise.
    """
    successful_uploads = [res.unwrap() for res in upload_results if res]
    failed_uploads = [res for res in upload_results if not res]
    if failed_uploads:
        if raise_on_error:
            # then raise the first exception in failed results
            for res in failed_uploads:
                exception = res.exception_or(SDSError("File Upload Failed"))
                if exception:
                    raise exception
        if verbose:
            log_user_error(f"Failed to upload the following files: {failed_uploads}")
        return False
    if not successful_uploads:
        if verbose:
            log_user_error("No files uploaded, unable to create capture.")
        return False
    return True
