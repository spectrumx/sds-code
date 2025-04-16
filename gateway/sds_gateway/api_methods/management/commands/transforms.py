# Define transform scripts for different field updates
rh_field_transforms = {
    "search_props.center_frequency": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.center_frequency != null) {
                ctx._source.search_props.center_frequency =
                    ctx._source.capture_props.center_frequency;
            }
        """.strip(),
        "lang": "painless",
    },
    "search_props.frequency_min": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.metadata != null &&
                ctx._source.capture_props.metadata.fmin != null) {
                ctx._source.search_props.frequency_min =
                    ctx._source.capture_props.metadata.fmin;
            }
        """.strip(),
        "lang": "painless",
    },
    "search_props.frequency_max": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.metadata != null &&
                ctx._source.capture_props.metadata.fmax != null) {
                ctx._source.search_props.frequency_max =
                    ctx._source.capture_props.metadata.fmax;
            }
        """.strip(),
        "lang": "painless",
    },
    "search_props.span": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.span != null) {
                ctx._source.search_props.span = ctx._source.capture_props.span;
            }
        """.strip(),
        "lang": "painless",
    },
    "search_props.gain": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.gain != null) {
                ctx._source.search_props.gain = ctx._source.capture_props.gain;
            }
        """.strip(),
        "lang": "painless",
    },
    "search_props.coordinates": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.latitude != null &&
                ctx._source.capture_props.longitude != null) {
                ctx._source.search_props.coordinates = [
                    ctx._source.capture_props.longitude,
                    ctx._source.capture_props.latitude
                ];
            }
        """.strip(),
        "lang": "painless",
    },
    "search_props.sample_rate": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.sample_rate != null) {
                ctx._source.search_props.sample_rate =
                    ctx._source.capture_props.sample_rate;
            }
        """.strip(),
        "lang": "painless",
    },
}

drf_field_transforms = {
    "search_props.center_frequency": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.center_freq != null) {
                ctx._source.search_props.center_frequency =
                    ctx._source.capture_props.center_freq;
            }
        """.strip(),
        "lang": "painless",
    },
    "search_props.frequency_min": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.center_freq != null &&
                ctx._source.capture_props.span != null &&
                ctx._source.search_props.frequency_min == null) {
                ctx._source.search_props.frequency_min =
                    ctx._source.capture_props.center_freq -
                    (ctx._source.capture_props.span / 2);
            }
        """.strip(),
        "lang": "painless",
    },
    "search_props.frequency_max": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.center_freq != null &&
                ctx._source.capture_props.span != null &&
                ctx._source.search_props.frequency_max == null) {
                ctx._source.search_props.frequency_max =
                    ctx._source.capture_props.center_freq +
                    (ctx._source.capture_props.span / 2);
            }
        """.strip(),
        "lang": "painless",
    },
    "search_props.start_time": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.start_bound != null &&
                ctx._source.search_props.start_time == null) {
                ctx._source.search_props.start_time =
                    ctx._source.capture_props.start_bound;
            }
        """.strip(),
        "lang": "painless",
    },
    "search_props.end_time": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.end_bound != null &&
                ctx._source.search_props.end_time == null) {
                ctx._source.search_props.end_time =
                    ctx._source.capture_props.end_bound;
            }
        """.strip(),
        "lang": "painless",
    },
    "search_props.span": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.span != null &&
                ctx._source.search_props.span == null) {
                ctx._source.search_props.span = ctx._source.capture_props.span;
            }
        """.strip(),
        "lang": "painless",
    },
    "search_props.gain": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.gain != null &&
                ctx._source.search_props.gain == null) {
                ctx._source.search_props.gain = ctx._source.capture_props.gain;
            }
        """.strip(),
        "lang": "painless",
    },
    "search_props.bandwidth": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.bandwidth != null &&
                ctx._source.search_props.bandwidth == null) {
                ctx._source.search_props.bandwidth =
                    ctx._source.capture_props.bandwidth;
            }
        """.strip(),
        "lang": "painless",
    },
    "search_props.sample_rate": {
        "source": """
            if (ctx._source.capture_props != null &&
                ctx._source.capture_props.sample_rate_numerator != null &&
                ctx._source.capture_props.sample_rate_denominator != null &&
                ctx._source.search_props.sample_rate == null) {
                ctx._source.search_props.sample_rate =
                    ctx._source.capture_props.sample_rate_numerator /
                    ctx._source.capture_props.sample_rate_denominator;
            }
        """.strip(),
        "lang": "painless",
    },
}
