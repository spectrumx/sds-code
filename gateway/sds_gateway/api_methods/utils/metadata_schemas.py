# ruff: noqa: E501
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
            "format": "date-time",
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
        "resolution_bandwidth": {
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
            "type": object,
            "description": "Custom attributes of the capture.",
        },
    },
    "index_mapping": {
        "sample_rate_numerator": {
            "type": "integer",
        },
        "sample_rate_denominator": {
            "type": "integer",
        },
        "samples_per_second": {
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
        "resolution_bandwidth": {
            "type": "integer",
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

capture_metadata_fields_by_type = {
    "drf": drf_capture_metadata_schema,
}
