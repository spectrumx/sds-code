import logging
import typing

import digital_rf as drf

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


def key_in_dict_partial(key, dictionary):
    """Check if a key is a partial match in the dictionary keys and return the full key."""  # noqa: E501
    for dict_key in dictionary:
        if key in dict_key:
            return True, dict_key
    return False, None


def read_metadata_by_channel(data_path, channel_name):
    """Reads Digital RF metadata file."""

    rf_reader = drf.DigitalRFReader(data_path)
    bounds_raw = rf_reader.get_bounds(channel_name)
    bounds_raw = typing.cast(tuple[int, int], bounds_raw)
    bounds = Bounds(start=bounds_raw[0], end=bounds_raw[1])

    # get properties
    drf_properties = rf_reader.get_properties(channel_name, bounds.start)

    # add bounds to properties, convert to unix timestamp
    drf_properties["start_bound"] = bounds.start / drf_properties["samples_per_second"]
    drf_properties["end_bound"] = bounds.end / drf_properties["samples_per_second"]

    # initialize the digital metadata reader
    md_reader = rf_reader.get_digital_metadata(channel_name)
    dmd_properties = md_reader.read_flatdict(
        start_sample=bounds.start,
        method="ffill",
    )

    # Merge the flattened dictionaries
    return {
        **drf_properties,
        **dmd_properties,
    }


def validate_metadata_by_channel(data_path, channel_name):
    # use the drf_capture_metadata_schema to validate the metadata
    validated_properties = {}
    props_by_channel = read_metadata_by_channel(data_path, channel_name)
    properties_to_validate = list(props_by_channel.keys())
    required_props = drf_capture_metadata_schema["required"]

    for key, value in drf_capture_metadata_schema["properties"].items():
        # check for partial match of key in schema (partial because some expected keys are nested) # noqa: E501
        partial_key_match, matched_key = key_in_dict_partial(key, props_by_channel)
        if partial_key_match:
            validated_properties[key] = props_by_channel[matched_key]
            properties_to_validate.remove(matched_key)
            # check value types and convert if necessary
            if not isinstance(validated_properties[key], value["type"]):
                if value["type"] is int:
                    try:
                        validated_properties[key] = int(validated_properties[key])
                    except ValueError:
                        msg = f"Could not convert '{key}' to int."
                        logging.warning(msg)
                if value["type"] is bool:
                    try:
                        validated_properties[key] = bool(validated_properties[key])
                    except ValueError:
                        msg = f"Could not convert '{key}' to bool."
                        logging.warning(msg)

        if key in required_props and key not in validated_properties:
            msg = f"Missing expected property '{key}' in metadata."
            logging.warning(msg)

    if len(properties_to_validate) > 0:
        msg = f"Unexpected properties found in metadata: {properties_to_validate}. These will be added to a custom_attrs field."  # noqa: E501
        logging.info(msg)
        # add the unexpected properties to a custom_attrs field
        validated_properties["custom_attrs"] = {
            k: props_by_channel[k] for k in properties_to_validate
        }

    return validated_properties
