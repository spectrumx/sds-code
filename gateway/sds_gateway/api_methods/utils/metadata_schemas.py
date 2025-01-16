# ruff: noqa: E501
# for full schema definition, see https://github.com/spectrumx/schema-definitions/blob/master/definitions/sds/metadata-formats/digital-rf/README.md
# the mapping below is used for drf capture metadata parsing in extract_drf_metadata.py
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
        "resolution_bandwidth",
        "antenna",
        "indoor_outdoor",
        "antenna_direction",
    ],
}

# fields to be explicitly mapped in the capture metadata index, see https://opensearch.org/docs/2.5/field-types/mappings/#explicit-mapping
drf_capture_index_mapping = {
    "sample_rate_numerator": {
        "type": "integer",
    },
    "sample_rate_denominator": {
        "type": "integer",
    },
    "samples_per_second": {
        "type": "integer",
    },
    "start_bound": {
        "type": "integer",
    },
    "end_bound": {
        "type": "integer",
    },
    "center_freq": {
        "type": "integer",
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
}

# for full schema definition, see https://github.com/spectrumx/schema-definitions/blob/master/definitions/sds/metadata-formats/radiohound/v0/schema.json
# full mapping is not used in this repo, but is provided here for reference
rh_capture_index_mapping = {
    "data_type": {
        "type": "text",
    },
    "fmin": {
        "type": "integer",
    },
    "fmax": {
        "type": "integer",
    },
    "xstart": {
        "type": "integer",
    },
    "xstop": {
        "type": "integer",
    },
    "sample_rate": {
        "type": "integer",
    },
    "center_frequency": {
        "type": "float",
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
        "type": "keyword",
    },
}

capture_index_mapping_by_type = {
    "drf": drf_capture_index_mapping,
    "rh": rh_capture_index_mapping,
}
