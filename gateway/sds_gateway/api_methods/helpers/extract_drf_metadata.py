import contextlib
import typing
from pathlib import Path

import digital_rf as drf
from loguru import logger as log

if typing.TYPE_CHECKING:
    from digital_rf.digital_metadata import DigitalMetadataReader

from sds_gateway.api_methods.utils.metadata_schemas import drf_capture_metadata_schema


class Bounds(typing.NamedTuple):
    """Represents a continuous range, inclusive."""

    start: int
    end: int

    def __postinit__(self, start: int, end: int) -> None:
        if start >= end:
            msg = f"Start '{start}' must be less than end '{end}'"
            raise ValueError(msg)

    @property
    def size(self) -> int:
        """Returns the size of the range (inclusive)."""
        return self.end - self.start + 1

    def __len__(self) -> int:
        """Alias for self.size."""
        return self.size


def key_in_dict_partial(
    key: str,
    dict_keys: typing.Iterable[str],
) -> str | None:
    """Checks if a key is a partial match in any of the dict keys passed.

    Returns:
        The matched key if a partial match is found, None otherwise.
    """
    for dict_key in dict_keys:
        if key in dict_key:
            return dict_key
    return None


def read_metadata_by_channel(data_path: Path, channel_name: str):
    """Reads Digital RF metadata file."""

    rf_reader = drf.DigitalRFReader(str(data_path))
    bounds_raw = rf_reader.get_bounds(channel_name)
    bounds_raw = typing.cast("tuple[int, int]", bounds_raw)
    bounds = Bounds(start=bounds_raw[0], end=bounds_raw[1])

    # get properties
    drf_properties = typing.cast(
        "dict[str, typing.Any]",
        rf_reader.get_properties(channel_name, bounds.start),
    )

    # add bounds to properties, convert to unix timestamp
    drf_properties["start_bound"] = bounds.start / drf_properties["samples_per_second"]
    drf_properties["end_bound"] = bounds.end / drf_properties["samples_per_second"]

    # initialize the digital metadata reader
    md_reader = typing.cast(
        "DigitalMetadataReader",
        rf_reader.get_digital_metadata(channel_name),
    )
    dmd_properties = md_reader.read_flatdict(
        start_sample=bounds.start,
        method="ffill",
    )
    if not isinstance(dmd_properties, dict):
        msg = "Expected dmd_properties to be a dictionary"
        raise TypeError(msg)

    # Merge the flattened dictionaries
    return {
        **drf_properties,
        **dmd_properties,
    }


def validate_metadata_by_channel(
    data_path: Path,
    channel_name: str,
) -> dict[str, typing.Any]:
    """Validates the metadata for a given channel."""
    # use the drf_capture_metadata_schema to validate the metadata
    validated_props = {}
    props_by_channel = read_metadata_by_channel(
        data_path=data_path,
        channel_name=channel_name,
    )
    props_pending_validation = list(props_by_channel.keys())
    required_props = drf_capture_metadata_schema["required"]

    for key, value in drf_capture_metadata_schema["properties"].items():
        # check for partial match of key in schema (some expected keys are nested)
        matched_key = key_in_dict_partial(
            key,
            dict_keys=props_by_channel.keys(),
        )
        if matched_key:
            original_value = props_by_channel[matched_key]
            props_pending_validation.remove(matched_key)

            # already in the correct type, skip
            target_type = value["type"]
            if isinstance(original_value, target_type):
                continue

            converted_or_none = convert_or_warn(
                name=key,
                value=original_value,
                target_type=target_type,
                should_raise=False,
            )
            if converted_or_none is not None:
                validated_props[key] = converted_or_none

        if key in required_props and key not in validated_props:
            msg = f"Missing expected property '{key}' in metadata."
            log.warning(msg)

    if len(props_pending_validation) > 0:
        msg = f"Unexpected properties found in metadata: {props_pending_validation}. These will be added to a custom_attrs field."  # noqa: E501
        log.info(msg)
        # add the unexpected properties to a custom_attrs field
        validated_props["custom_attrs"] = {
            k: props_by_channel[k] for k in props_pending_validation
        }

    return validated_props


T = typing.TypeVar("T", int, bool)


def convert_or_warn(
    *,
    value: typing.Any,
    target_type: type[T],
    cast_fn: typing.Callable[[T], T] | None = None,
    name: str = "",
    should_raise: bool = False,
) -> T | None:
    """Converts the passed value to the desired type.

    Args:
        value:          The value to convert.
        target_type:    The type to convert the value to.
        cast_fn:        The function to use for casting the value. \
                        If None, target_type is called.
        name:           The name of the value for logging purposes.
        should_raise:   Whether to raise a ValueError if the conversion fails.
    Returns:
        The converted value if successful, None otherwise.
    Raises:
        ValueError: If the conversion fails and should_raise is True.
    """
    converted_value = None
    with contextlib.suppress(ValueError):
        if callable(cast_fn):
            converted_value = cast_fn(value)
        elif callable(target_type):
            converted_value = target_type(value)
        else:  # pragma: no cover
            msg = f"Type {type(value)} of '{name}' does not have a conversion method."
            log.warning(msg)
    if not isinstance(converted_value, target_type):
        msg = f"Could not convert '{name}={value}' to type {cast_fn}."
        log.warning(msg)
        if should_raise:
            raise ValueError(msg)
        return None
    return converted_value
