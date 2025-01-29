# This is PEP-723-compatible script: https://peps.python.org/pep-0723/
# You can run it with uv without manually installing its dependencies:
#   uv run rh-schema-generator.py
# Which will run a self-test and create the `<VERSION>/schema.json` file.

# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "numpy>=2.1.0",
#     "pydantic>=2.0.0",
#     "rich",
#     "ruff",
# ]
# ///
import ast
import base64
import datetime
import json
import logging
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Annotated
from typing import Any

import numpy as np
from numpy.typing import NDArray
from pydantic import AfterValidator
from pydantic import AliasChoices
from pydantic import BaseModel
from pydantic import BeforeValidator
from pydantic import ConfigDict
from pydantic import Field
from pydantic import PlainSerializer
from pydantic import model_validator
from pydantic.json_schema import SkipJsonSchema
from rich.console import Console

console = Console()
DEFAULT_EXTENSION = ".rh.json"
FORMAT_VERSION = "v0"
MAX_INT_SIZE = int(2**63 - 1)


def log_warning(msg: str) -> None:
    """Log a warning message."""
    logging.warning("%s", msg)


def serialize_data(v: bytes) -> str:
    """Serialize data to a base64 string."""
    return base64.b64encode(v).decode()


def serialize_type(v: "NumpyDType") -> str:  # type: ignore[valid-type]
    return v.value


def validate_mac_address(v: str) -> str:
    pattern = r"^[0-9A-Fa-f]+$"
    if not re.match(pattern=pattern, string=v):
        msg = "MAC address must be a hexadecimal string with no separators"
        raise ValueError(msg)
    return v


def validate_timestamp(v: datetime.datetime) -> datetime.datetime:
    # make sure it has timezone info, defaulting to UTC when missing
    if not v.tzinfo:
        msg = "Timestamp must have timezone information. Assuming UTC."
        log_warning(msg)
        now_utc = datetime.datetime.now(datetime.UTC)
        v = v.replace(tzinfo=now_utc.tzinfo)
    return v


def validate_version_after(v: str) -> str:
    # make sure that, if present, it's a valid version string
    pattern = r"^v[0-9]+$"
    if not re.match(pattern=pattern, string=v):
        msg = "Invalid version format"
        raise ValueError(msg)
    return v


def validate_data(v: str) -> bytes:
    """Make sure data is a valid base64 encoding."""
    if not v:
        msg = "Data must not be empty"
        raise ValueError(msg)
    try:
        buffer = base64.b64decode(v)
    except Exception as err:
        msg = "Data must be base64 encoded"
        raise ValueError(msg) from err
    return buffer


class DataType(Enum):
    """Data types supported by RadioHound."""

    PERIODOGRAM = "periodogram"


def validate_data_type(v: str) -> DataType:
    try:
        return DataType(v)
    except ValueError as err:
        msg = "Invalid data type"
        raise ValueError(msg) from err


class _RHMetadataV0(BaseModel):
    """Metadata for a RadioHound capture."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    data_type: Annotated[
        DataType,
        AfterValidator(validate_data_type),
        Field(description="The category of this capture"),
    ]
    fmax: Annotated[
        int,
        Field(description="The maximum frequency in the sample", gt=0, lt=MAX_INT_SIZE),
    ]
    fmin: Annotated[
        int,
        Field(description="The minimum frequency in the sample", gt=0, lt=MAX_INT_SIZE),
    ]
    gps_lock: Annotated[
        bool,
        Field(
            description=(
                "Whether a GPS satellite lock is obtained, "
                "otherwise the last known coordinates"
            ),
        ),
    ]
    nfft: Annotated[
        int,
        Field(description="Number of FFT bins, recommended to be a power of 2", gt=0),
    ]
    scan_time: Annotated[
        float,
        Field(description="The time taken to scan this sample, in seconds", gt=0),
    ]

    # deprecated metadata attributes

    xcount: Annotated[
        int | None,
        Field(
            description="The number of points in the periodogram",
            gt=0,
            lt=MAX_INT_SIZE,
            deprecated=True,
            exclude=True,
            default=None,
        ),
    ]
    xstart: Annotated[
        int | None,
        Field(
            description="The start frequency of the periodogram",
            gt=0,
            lt=MAX_INT_SIZE,
            deprecated=True,
            exclude=True,
            default=None,
        ),
    ]
    xstop: Annotated[
        int | None,
        Field(
            description="The stop frequency of the periodogram",
            gt=0,
            lt=MAX_INT_SIZE,
            deprecated=True,
            exclude=True,
            default=None,
        ),
    ]

    # moved and optional attributes
    archive_result: Annotated[
        bool | None,
        Field(
            description="Whether the data was archived",
            validation_alias=AliasChoices("archive_result", "archiveResult"),
            default=None,
        ),
    ]


def all_dtypes() -> set[str]:
    """Return all numpy-compatible data types."""
    return {dtype.__name__ for dtype in np.sctypeDict.values()}


NumpyDType = Enum("NumpyDTypes", {dtype: dtype for dtype in all_dtypes()})


def validate_type(v: str) -> "NumpyDType":  # type: ignore[valid-type]
    if v not in NumpyDType.__members__:
        msg = f"Invalid data type: {v}"
        raise ValueError(msg)
    return NumpyDType.__members__[v]


def nd_array_before_validator(x: str | list[Any]) -> NDArray[Any]:  # type: ignore[return-value]
    # custom before validation logic
    if isinstance(x, str):
        x_list = ast.literal_eval(x)
        x = np.array(x_list)  # type: ignore[assignment]
    if isinstance(x, list):
        x = np.array(x)  # type: ignore[assignment]
    return x  # type: ignore[return-value]


def nd_array_serializer(x) -> list:
    return x.tolist()


class _RadioHoundDataV0(BaseModel):
    """Describes a RadioHound capture."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        json_schema_extra={
            "$id": "https://json.schemastore.org/radiohound-v0.json",
            "$schema": "http://json-schema.org/draft-07/schema#",
        },
    )

    # required attributes
    data: Annotated[
        bytes,
        AfterValidator(validate_data),
        PlainSerializer(serialize_data),
    ]
    data_as_numpy: Annotated[
        SkipJsonSchema[None],
        np.ndarray,
        Field(default=None, exclude=True),
        BeforeValidator(nd_array_before_validator),
        PlainSerializer(nd_array_serializer, return_type=list),
    ]
    gain: float
    latitude: Annotated[
        float,
        Field(
            description="The latitude where the data was captured, in decimal degrees",
            gt=-90,
            lt=90,
        ),
    ]
    longitude: Annotated[
        float,
        Field(
            description="The longitude where the data was captured, in decimal degrees",
            gt=-180,
            lt=180,
        ),
    ]
    mac_address: Annotated[
        str,
        AfterValidator(validate_mac_address),
        Field(
            description="MAC address of the device, without separators",
            min_length=12,
            max_length=12,
        ),
    ]
    metadata: Annotated[_RHMetadataV0, Field(description="Metadata for this capture")]
    sample_rate: Annotated[
        int,
        Field(description="Sample rate of the capture, in Hz", gt=0, lt=MAX_INT_SIZE),
    ]
    short_name: Annotated[
        str,
        Field(description="The short name of the device", max_length=255),
    ]
    timestamp: Annotated[
        datetime.datetime,
        AfterValidator(validate_timestamp),
        Field(
            description=(
                "Timestamp of the capture start, as ISO 8601 with timezone information"
            ),
        ),
    ]

    type: Annotated[
        str,
        AfterValidator(validate_type),
        PlainSerializer(serialize_type),
        Field(description="Numpy-compatible dtype of `data` elements"),
    ]
    version: Annotated[
        str,
        AfterValidator(validate_version_after),
        Field(
            description="Version of the RadioHound data format",
            max_length=255,
            default="v0",
        ),
    ]

    # optional attributes
    altitude: Annotated[
        float | None,
        Field(
            description="The altitude where the data was captured, in meters",
            default=None,
        ),
    ]
    batch: Annotated[
        int | None,
        Field(
            description="Can be used to group scans together",
            default=None,
        ),
    ]
    center_frequency: Annotated[
        float | None,
        Field(
            description=(
                "The center frequency of the capture, "
                "calculated as the mean of the start and end frequencies"
            ),
            default=None,
        ),
    ]
    custom_fields: Annotated[
        dict[str, Any],
        Field(
            description="Custom fields that are not part of the standard schema",
            default_factory=dict,
        ),
    ]
    hardware_board_id: Annotated[
        str | None,
        Field(
            description="The hardware board ID of the device capturing the data",
            max_length=255,
            default=None,
        ),
    ]
    hardware_version: Annotated[
        str | None,
        Field(
            description="The hardware version of the device capturing the data",
            max_length=255,
            default=None,
        ),
    ]
    software_version: Annotated[
        str | None,
        Field(
            description="The software version of the device capturing the data",
            max_length=255,
            default=None,
        ),
    ]

    # deprecated attributes
    suggested_gain: Annotated[
        float | None,
        Field(
            description="Suggested gain for the device",
            gt=0,
            deprecated=True,
            exclude=True,
            default=None,
        ),
    ]
    uncertainty: Annotated[
        int | None,
        Field(
            description="Uncertainty of the measurement",
            gt=0,
            deprecated=True,
            exclude=True,
            default=None,
        ),
    ]

    # moved optional attributes (using root validators)

    @model_validator(mode="before")
    @classmethod
    def move_requested_to_custom_fields(cls, values: dict) -> dict:
        """Introduced in v0."""
        requested = values.get("requested")
        if requested:
            if "custom_fields" not in values:
                values["custom_fields"] = {}
            values["custom_fields"]["requested"] = requested
            del values["requested"]
        return values

    requested: Annotated[
        dict | None,
        # we don't care to validate `requested` contents
        # as it's been moved to custom_fields
        Field(
            description="Attributes set by requestor",
            exclude=True,
            default=None,
        ),
        PlainSerializer(
            lambda v: {"custom_fields": {"requested": v}} if v else None,
            return_type=dict,
        ),
    ]

    def model_post_init(self, _: Any) -> None:
        self.data_as_numpy = np.frombuffer(self.data, dtype=self.type.value)

    def to_file(self, file_path: Path | str | bytes) -> None:
        """Write the RadioHound data to a file."""
        obj = self.model_dump(mode="json")
        file_path_real: Path

        if isinstance(file_path, bytes):
            file_path_real = Path(file_path.decode())
        elif isinstance(file_path, str):
            file_path_real = Path(file_path)
        else:  # Path
            file_path_real = file_path  # type: ignore[valid-type]

        # if file_path_real has no extension, use .rh.json
        if not file_path_real.suffix:
            file_path_real = file_path_real.with_suffix(DEFAULT_EXTENSION)
        with file_path_real.open(mode="w", encoding="utf-8") as fp:
            json.dump(obj, fp=fp, indent=4, sort_keys=True)


def load_rh_file_v0(file_path: Path | str | bytes) -> _RadioHoundDataV0:
    """Loads a valid RadioHound file into memory.

    Args:
        file_path:  Path to a valid RadioHound file to load.
    Returns:
        The loaded RadioHound data.
    Raises:
        FileNotFoundError: If the file does not exist.
        ValidationError: If the file is not a valid RadioHound file.
    """
    file_path_real: Path
    if isinstance(file_path, bytes):
        file_path_real = Path(file_path.decode())
    elif isinstance(file_path, str):
        file_path_real = Path(file_path)
    else:  # must be Path since we've exhausted other types
        file_path_real = file_path  # type: ignore[valid-type]

    if not file_path_real.exists():
        msg = f"File not found: {file_path_real}"
        raise FileNotFoundError(msg)
    with file_path_real.open(mode="rb") as fp:
        return _RadioHoundDataV0.model_validate_json(json_data=fp.read())


def _self_test(*, verbose: bool = False) -> None:
    """Run self-tests."""
    sample_dir = Path(FORMAT_VERSION) / "samples"
    sample_file = (sample_dir / "obsolete-full").with_suffix(DEFAULT_EXTENSION)
    if verbose:
        console.print("\n\nRUNNING SELF-TESTS")
    if verbose:
        console.print(f"\tLoading sample file: {sample_file}")
    loaded_model = load_rh_file_v0(sample_file)
    if verbose:
        console.print("\n\nDUMPED SAMPLE:")
        console.print(loaded_model.model_dump_json(indent=4))
        console.print("\n\nNUMPY DATA:")
        console.print(
            f"Shape: {loaded_model.data_as_numpy.shape}, "
            f"dtype: {loaded_model.data_as_numpy.dtype}",
        )
    # dump it to a file to create a reference format for this version
    reference_file = sample_file.parent / f"reference-{FORMAT_VERSION}"
    console.print(f"Writing reference file: {reference_file}")
    loaded_model.to_file(file_path=reference_file)


def _dump_schema(
    model: type[BaseModel],
    file_path: Path,
    *,
    verbose: bool = False,
) -> None:
    """Dump the JSON schema for a model."""
    json_schema = model.model_json_schema(mode="validation")
    if verbose:
        console.print("\n\nSCHEMA:")
        console.print(json_schema)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open(mode="w", encoding="utf-8") as fp:
        json.dump(json_schema, fp=fp, indent=4)


def main() -> None:
    """Entry point to generate the JSON schema."""
    console.print(f"Python interpreter path: {sys.executable}")
    _self_test(verbose=True)
    schema_path = Path(FORMAT_VERSION) / "schema.json"
    _dump_schema(model=_RadioHoundDataV0, file_path=schema_path, verbose=True)


if __name__ == "__main__":
    main()

RadioHoundData = _RadioHoundDataV0
load_rh_file = load_rh_file_v0

__all__ = ["RadioHoundData", "load_rh_file_v0", "main"]
