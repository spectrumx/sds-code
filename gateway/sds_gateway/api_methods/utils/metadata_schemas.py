# ruff: noqa: E501
# for full schema definition, see https://github.com/spectrumx/schema-definitions/blob/master/definitions/sds/metadata-formats/digital-rf/README.md
# the mapping below is used for drf capture metadata parsing in extract_drf_metadata.py

from sds_gateway.api_methods.models import CaptureType

drf_capture_metadata_schema = {
    "properties": {
        "H5Tget_class": {
            "type": int,
            "description": "The result of the H5Tget_class function.",
        },
        "H5Tget_size": {
            "type": int,
            "description": "The result of the H5Tget_size function.",
        },
        "H5Tget_order": {
            "type": int,
            "description": "The result of the H5Tget_order function.",
        },
        "H5Tget_precision": {
            "type": int,
            "description": "The result of the H5Tget_precision function.",
        },
        "H5Tget_offset": {
            "type": int,
            "description": "The result of the H5Tget_offset function.",
        },
        "subdir_cadence_secs": {
            "type": int,
            "description": "The cadence of the subdirectory in seconds.",
        },
        "file_cadence_millisecs": {
            "type": int,
            "description": "The cadence of the file in milliseconds.",
        },
        "sample_rate_numerator": {
            "type": int,
            "description": "The numerator of the sample rate.",
        },
        "sample_rate_denominator": {
            "type": int,
            "description": "The denominator of the sample rate.",
        },
        "samples_per_second": {
            "type": int,
            "description": "The samples per second.",
        },
        "start_bound": {
            "type": int,
            "description": "The start time (unix timestamp) of a capture.",
        },
        "end_bound": {
            "type": int,
            "description": "The end time (unix timestamp) of a capture.",
        },
        "is_complex": {
            "type": bool,
            "description": "Whether the capture is complex.",
        },
        "is_continuous": {
            "type": bool,
            "description": "Whether the capture is continuous.",
        },
        "epoch": {
            "type": str,
            "description": "The linux epoch.",
        },
        "digital_rf_time_description": {
            "type": str,
            "description": "The time description of digital_rf.",
        },
        "digital_rf_version": {
            "type": str,
            "description": "The version of digital_rf.",
        },
        "sequence_num": {
            "type": int,
            "description": "running number from start of acquisition.",
        },
        "init_utc_timestamp": {
            "type": int,
            "description": "UTC timestamp of each restart of the recorder; needed if leap seconds correction applied.",
        },
        "computer_time": {
            "type": int,
            "description": "Computer time at creation of individual RF file (unix time).",
        },
        "uuid_str": {
            "type": str,
            "description": "UUID of the capture; set independently at each restart of the recorder.",
        },
        "center_freq": {
            "type": int,
            "description": "The center frequency of the capture.",
        },
        "span": {
            "type": int,
            "description": "The span of the capture.",
        },
        "gain": {
            "type": float,
            "description": "The gain of the capture.",
        },
        "bandwidth": {
            "type": int,
            "description": "The resolution bandwidth of the capture.",
        },
        "antenna": {
            "type": str,
            "description": "The antenna used in the capture.",
        },
        "indoor_outdoor": {
            "type": str,
            "description": "Whether the capture was taken indoors or outdoors.",
        },
        "antenna_direction": {
            "type": float,
            "description": "The direction of the antenna.",
        },
        "custom_attrs": {
            "type": dict,
            "description": "Custom attributes of the capture.",
        },
    },
    "required": [
        "H5Tget_class",
        "H5Tget_size",
        "H5Tget_order",
        "H5Tget_precision",
        "H5Tget_offset",
        "subdir_cadence_secs",
        "file_cadence_millisecs",
        "sample_rate_numerator",
        "sample_rate_denominator",
        "samples_per_second",
        "start_bound",
        "end_bound",
        "is_complex",
        "is_continuous",
        "epoch",
        "digital_rf_time_description",
        "digital_rf_version",
        "center_freq",
        "span",
        "gain",
        "bandwidth",
        "antenna",
        "indoor_outdoor",
        "antenna_direction",
    ],
}

# fields to be explicitly mapped in the capture metadata index, see https://opensearch.org/docs/2.5/field-types/mappings/#explicit-mapping
drf_capture_index_mapping = {
    "H5Tget_class": {
        "type": "integer",
    },
    "H5Tget_size": {
        "type": "integer",
    },
    "H5Tget_order": {
        "type": "integer",
    },
    "H5Tget_precision": {
        "type": "integer",
    },
    "H5Tget_offset": {
        "type": "integer",
    },
    "subdir_cadence_secs": {
        "type": "integer",
    },
    "file_cadence_millisecs": {
        "type": "integer",
    },
    "sample_rate_numerator": {
        "type": "long",
    },
    "sample_rate_denominator": {
        "type": "long",
    },
    "samples_per_second": {
        "type": "long",
    },
    "start_bound": {
        "type": "long",
    },
    "end_bound": {
        "type": "long",
    },
    "is_complex": {
        "type": "boolean",
    },
    "is_continuous": {
        "type": "boolean",
    },
    "epoch": {
        "type": "keyword",
    },
    "digital_rf_time_description": {
        "type": "keyword",
    },
    "digital_rf_version": {
        "type": "keyword",
    },
    "sequence_num": {
        "type": "integer",
    },
    "init_utc_timestamp": {
        "type": "integer",
    },
    "computer_time": {
        "type": "integer",
    },
    "uuid_str": {
        "type": "keyword",
    },
    "center_freq": {
        "type": "double",
    },
    "span": {
        "type": "integer",
    },
    "gain": {
        "type": "float",
    },
    "bandwidth": {
        "type": "integer",
    },
    "antenna": {
        "type": "text",
    },
    "indoor_outdoor": {
        "type": "keyword",
    },
    "antenna_direction": {
        "type": "float",
    },
    "custom_attrs": {
        "type": "nested",
    },
}

# for full schema definition, see https://github.com/spectrumx/schema-definitions/blob/master/definitions/sds/metadata-formats/radiohound/v0/schema.json
# full mapping is not used in this repo, but is provided here for reference
rh_capture_index_mapping = {
    "metadata": {
        "type": "nested",
        "properties": {
            "archive_result": {
                "type": "boolean",
            },
            "data_type": {
                "type": "keyword",
            },
            "fmax": {
                "type": "double",
            },
            "fmin": {
                "type": "double",
            },
            "gps_lock": {
                "type": "boolean",
            },
            "nfft": {
                "type": "integer",
            },
            "scan_time": {
                "type": "float",
            },
        },
    },
    "sample_rate": {
        "type": "long",
    },
    "center_frequency": {
        "type": "double",
    },
    "latitude": {
        "type": "float",
    },
    "longitude": {
        "type": "float",
    },
    "altitude": {
        "type": "float",
    },
    "mac_address": {
        "type": "keyword",
    },
    "short_name": {
        "type": "text",
    },
    "custom_fields": {
        "type": "nested",
        "properties": {
            "requested": {
                "type": "nested",
                "properties": {
                    "fmax": {
                        "type": "double",
                    },
                    "fmin": {
                        "type": "double",
                    },
                    "gain": {
                        "type": "float",
                    },
                    "samples": {
                        "type": "integer",
                    },
                },
            }
        },
    },
    "hardware_board_id": {
        "type": "keyword",
    },
    "hardware_version": {
        "type": "keyword",
    },
    "software_version": {
        "type": "keyword",
    },
    "timestamp": {
        "type": "date",
    },
    "type": {
        "type": "keyword",
    },
    "version": {
        "type": "keyword",
    },
}

base_index_fields = [
    "channel",
    "scan_group",
    "capture_type",
    "created_at",
    "capture_props",
]

capture_index_mapping_by_type = {
    CaptureType.DigitalRF: drf_capture_index_mapping,
    CaptureType.RadioHound: rh_capture_index_mapping,
}

base_properties = {
    "channel": {"type": "keyword"},
    "scan_group": {"type": "keyword"},
    "capture_type": {"type": "keyword"},
    "created_at": {"type": "date"},
    "is_deleted": {"type": "boolean"},
    "deleted_at": {"type": "date"},
}

search_properties = {
    "center_frequency": {"type": "double"},
    "frequency_min": {"type": "double"},
    "frequency_max": {"type": "double"},
    "start_time": {"type": "long"},  # unix timestamp
    "end_time": {"type": "long"},  # unix timestamp
    "span": {"type": "integer"},
    "gain": {"type": "float"},
    "bandwidth": {"type": "integer"},
    "coordinates": {"type": "geo_point"},
    "sample_rate": {"type": "long"},
}


def get_mapping_by_capture_type(capture_type: CaptureType) -> dict:
    """Get the mapping for a given capture type."""

    return {
        "properties": {
            **base_properties,
            "capture_props": {
                "type": "nested",
                "properties": capture_index_mapping_by_type[capture_type],
            },
            "search_props": {
                "type": "nested",
                "properties": search_properties,
            },
        },
    }
