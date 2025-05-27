import sys

# python 3.10 backport
if sys.version_info < (3, 11):  # noqa: UP036
    from backports.strenum import StrEnum  # noqa: UP035 # Required backport
else:
    from enum import StrEnum

from typing import Annotated
from typing import Any

from pydantic import BeforeValidator
from pydantic import Field
from pydantic import PlainSerializer
from pydantic import SerializationInfo
from pydantic import StringConstraints
from pydantic import TypeAdapter

PermissionOct = Annotated[
    int,
    Field(
        ge=0,
        le=511,
        description="Octal representation of Unix file permissions (e.g., 0x755).",
        examples=["0o755", "0o644", "0o777"],
    ),
]

PermissionStr = Annotated[
    str,
    Field(
        description="Unix file permission string (e.g. 'rwxr-xr--')",
        examples=["rwxr-xr-x", "rw-r--r--", "rwx------"],
    ),
    StringConstraints(
        strip_whitespace=True, min_length=9, max_length=9, pattern=r"^[rwx-]{9}$"
    ),
]
PermissionStrAdapter = TypeAdapter(PermissionStr)


# Helper functions
def octal_to_unix_perm_string(value: int) -> str:
    """
    Convert an octal Unix file permission to a string representation.

    :param value: An int representing the file permission in octal format (e.g., 0o755)
    :return: A 9-character string representing Unix permissions (e.g., 'rwxr-xr-x')
    :raises ValueError: If the input is not a valid octal Unix permission.
    """
    perm_oct = TypeAdapter(PermissionOct).validate_python(value)

    mapping = {
        0: "---",
        1: "--x",
        2: "-w-",
        3: "-wx",
        4: "r--",
        5: "r-x",
        6: "rw-",
        7: "rwx",
    }

    return "".join(mapping[(perm_oct >> (3 * i)) & 0o7] for i in reversed(range(3)))


def unix_perm_string_to_octal(value: str) -> int | ValueError:
    """
    Convert a Unix permission string (e.g., 'rwxr-xr-x') to an octal integer.

    :param value: A 9-character Unix permission string (e.g., 'rw-r--r--')
    :return: An integer representing the octal value of the permission (e.g., 0o755)
    :raises ValueError: If the input string is not a valid Unix permission string.
    """
    perm_str = PermissionStrAdapter.validate_python(value)

    one_hot = "".join(["0" if flag == "-" else "1" for flag in perm_str])
    return int(one_hot, base=2)


def unix_perm_from_any(value: Any) -> str | ValueError:
    if isinstance(value, int):
        return octal_to_unix_perm_string(value)
    if isinstance(value, str):
        return PermissionStrAdapter.validate_python(value)

    msg = f"Invalid Unix permission format: {value}"
    return ValueError(msg)


class PermissionRepresentation(StrEnum):
    STRING = "string"
    OCTAL = "octal"

    @classmethod
    def _missing_(cls, value):
        """Raises an exception when an unknown value is provided."""
        msg = f"Invalid PermissionRepresentation value: {value}"
        raise ValueError(msg)

    def convert(self, value: str) -> str:
        if self == PermissionRepresentation.OCTAL:
            return f"0o{unix_perm_string_to_octal(value):03o}"
        return value


# Serialization
def serialize_unix_permission(value: Any, info: SerializationInfo):
    """Serialize Unix permission based on context (`octal` or `string`)."""

    # If we have no context return the string representation
    if info.context is None:
        return value

    # Get the mode from the context and default to string
    mode = info.context.get("mode", PermissionRepresentation.STRING)
    return PermissionRepresentation(mode).convert(value)


UnixPermissionStr = Annotated[
    PermissionOct | PermissionStr,
    BeforeValidator(unix_perm_from_any),
    PlainSerializer(serialize_unix_permission, return_type=str),
]

__all__ = ["PermissionRepresentation", "UnixPermissionStr"]
