from pathlib import Path
from pathlib import PurePath
from pathlib import PurePosixPath
from typing import Annotated
from typing import Union

from pydantic import AfterValidator
from pydantic import BeforeValidator
from pydantic import Field
from pydantic import StringConstraints
from pydantic import TypeAdapter


def validate_path_string(value: str) -> str:
    if "\\" in value:
        raise ValueError("SDS Directory must not contain backslashes")
    return value


SDSDirectoryStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4096),
    AfterValidator(validate_path_string),
]

SDSDirectory = Annotated[
    PurePosixPath,  # Enforce that this field is always a PurePosixPath
    Field(
        description="The virtual directory on SpectrumX Data System",
        examples=["/my/upload/location"],
    ),
    BeforeValidator(
        lambda v: TypeAdapter(SDSDirectoryStr).validate_python(str(v))
    ),  # Ensure conversion happens
]

SDSDirectoryInput = Union[SDSDirectory, PurePath, Path, str]

__all__ = ["SDSDirectory", "SDSDirectoryInput"]
