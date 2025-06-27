from loguru import logger as log
from opensearchpy import ConnectionError as OpensearchConnectionError
from opensearchpy import RequestError

from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client


class Transforms:
    def __init__(self, capture_type: CaptureType):
        self.capture_type = capture_type
        self.client = get_opensearch_client()

        self.rh_field_transforms = {
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

        self.drf_field_transforms = {
            "search_props.center_frequency": {
                "source": """
                    if (ctx._source.search_props.center_frequency == null) {
                        ctx._source.search_props.center_frequency = [];
                    }

                    // Collect all center frequencies from capture_props
                    // (backward compatibility)
                    if (ctx._source.capture_props != null) {
                        if (ctx._source.capture_props.center_freq != null) {
                            if (!ctx._source.search_props.center_frequency
                                .contains(ctx._source.capture_props.center_freq)) {
                                ctx._source.search_props.center_frequency
                                    .add(ctx._source.capture_props.center_freq);
                            }
                        }
                        if (ctx._source.capture_props.center_frequencies != null) {
                            for (freq in ctx._source.capture_props
                                .center_frequencies) {
                                if (!ctx._source.search_props.center_frequency
                                    .contains(freq)) {
                                    ctx._source.search_props.center_frequency
                                        .add(freq);
                                }
                            }
                        }
                    }

                    // Collect all center frequencies from channels
                    // (multi-channel support)
                    if (ctx._source.channels != null) {
                        for (channel in ctx._source.channels) {
                            if (channel.channel_props != null) {
                                if (channel.channel_props.center_freq != null) {
                                    if (!ctx._source.search_props
                                        .center_frequency.contains(
                                            channel.channel_props.center_freq)) {
                                        ctx._source.search_props
                                            .center_frequency.add(
                                                channel.channel_props.center_freq);
                                    }
                                }
                                if (channel.channel_props.center_frequencies
                                    != null) {
                                    for (freq in channel.channel_props
                                        .center_frequencies) {
                                        if (!ctx._source.search_props
                                            .center_frequency.contains(freq)) {
                                            ctx._source.search_props
                                                .center_frequency.add(freq);
                                        }
                                    }
                                }
                            }
                        }
                    }""".strip(),
                "lang": "painless",
            },
            "search_props.frequency_min": {
                "source": """
                    if (ctx._source.search_props.frequency_min == null) {
                        ctx._source.search_props.frequency_min = [];
                    }

                    // Collect all frequency_min values from capture_props
                    // (backward compatibility)
                    if (ctx._source.capture_props != null) {
                        if (ctx._source.capture_props.center_freq != null &&
                            ctx._source.capture_props.span != null) {
                            double min_freq = ctx._source.capture_props
                                .center_freq - (ctx._source.capture_props.span
                                / 2.0);
                            if (!ctx._source.search_props.frequency_min
                                .contains(min_freq)) {
                                ctx._source.search_props.frequency_min
                                    .add(min_freq);
                            }
                        }
                        if (ctx._source.capture_props.center_frequencies
                            != null && ctx._source.capture_props.span
                            != null) {
                            for (freq in ctx._source.capture_props
                                .center_frequencies) {
                                double min_freq = freq - (ctx._source
                                    .capture_props.span / 2.0);
                                if (!ctx._source.search_props.frequency_min
                                    .contains(min_freq)) {
                                    ctx._source.search_props.frequency_min
                                        .add(min_freq);
                                }
                            }
                        }
                    }

                    // Collect all frequency_min values from channels
                    // (multi-channel support)
                    if (ctx._source.channels != null) {
                        for (channel in ctx._source.channels) {
                            if (channel.channel_props != null) {
                                if (channel.channel_props.center_freq != null &&
                                    channel.channel_props.span != null) {
                                    double min_freq = channel.channel_props
                                        .center_freq - (channel.channel_props
                                        .span / 2.0);
                                    if (!ctx._source.search_props.frequency_min
                                        .contains(min_freq)) {
                                        ctx._source.search_props.frequency_min
                                            .add(min_freq);
                                    }
                                }
                                if (channel.channel_props.center_frequencies
                                    != null && channel.channel_props.span
                                    != null) {
                                    for (freq in channel.channel_props
                                        .center_frequencies) {
                                        double min_freq = freq - (channel
                                            .channel_props.span / 2.0);
                                        if (!ctx._source.search_props
                                            .frequency_min.contains(min_freq)) {
                                            ctx._source.search_props
                                                .frequency_min.add(min_freq);
                                        }
                                    }
                                }
                            }
                        }
                    }
                """.strip(),
                "lang": "painless",
            },
            "search_props.frequency_max": {
                "source": """
                    if (ctx._source.search_props.frequency_max == null) {
                        ctx._source.search_props.frequency_max = [];
                    }

                    // Collect all frequency_max values from capture_props
                    // (backward compatibility)
                    if (ctx._source.capture_props != null) {
                        if (ctx._source.capture_props.center_freq != null &&
                            ctx._source.capture_props.span != null) {
                            double max_freq = ctx._source.capture_props
                                .center_freq + (ctx._source.capture_props.span
                                / 2.0);
                            if (!ctx._source.search_props.frequency_max
                                .contains(max_freq)) {
                                ctx._source.search_props.frequency_max
                                    .add(max_freq);
                            }
                        }
                        if (ctx._source.capture_props.center_frequencies
                            != null && ctx._source.capture_props.span
                            != null) {
                            for (freq in ctx._source.capture_props
                                .center_frequencies) {
                                double max_freq = freq + (ctx._source
                                    .capture_props.span / 2.0);
                                if (!ctx._source.search_props.frequency_max
                                    .contains(max_freq)) {
                                    ctx._source.search_props.frequency_max
                                        .add(max_freq);
                                }
                            }
                        }
                    }

                    // Collect all frequency_max values from channels
                    // (multi-channel support)
                    if (ctx._source.channels != null) {
                        for (channel in ctx._source.channels) {
                            if (channel.channel_props != null) {
                                if (channel.channel_props.center_freq != null &&
                                    channel.channel_props.span != null) {
                                    double max_freq = channel.channel_props
                                        .center_freq + (channel.channel_props
                                        .span / 2.0);
                                    if (!ctx._source.search_props.frequency_max
                                        .contains(max_freq)) {
                                        ctx._source.search_props.frequency_max
                                            .add(max_freq);
                                    }
                                }
                                if (channel.channel_props.center_frequencies
                                    != null && channel.channel_props.span
                                    != null) {
                                    for (freq in channel.channel_props
                                        .center_frequencies) {
                                        double max_freq = freq + (channel
                                            .channel_props.span / 2.0);
                                        if (!ctx._source.search_props
                                            .frequency_max.contains(max_freq)) {
                                            ctx._source.search_props
                                                .frequency_max.add(max_freq);
                                        }
                                    }
                                }
                            }
                        }
                    }
                """.strip(),
                "lang": "painless",
            },
            "search_props.start_time": {
                "source": """
                    if (ctx._source.search_props.start_time == null) {
                        ctx._source.search_props.start_time = [];
                    }

                    // Collect all start_time values from capture_props
                    // (backward compatibility)
                    if (ctx._source.capture_props != null &&
                        ctx._source.capture_props.start_bound != null) {
                        if (!ctx._source.search_props.start_time.contains(
                            ctx._source.capture_props.start_bound)) {
                            ctx._source.search_props.start_time.add(
                                ctx._source.capture_props.start_bound);
                        }
                    }

                    // Collect all start_time values from channels
                    // (multi-channel support)
                    if (ctx._source.channels != null) {
                        for (channel in ctx._source.channels) {
                            if (channel.channel_props != null &&
                                channel.channel_props.start_bound != null) {
                                if (!ctx._source.search_props.start_time
                                    .contains(channel.channel_props.start_bound)) {
                                    ctx._source.search_props.start_time.add(
                                        channel.channel_props.start_bound);
                                }
                            }
                        }
                    }
                """.strip(),
                "lang": "painless",
            },
            "search_props.end_time": {
                "source": """
                    if (ctx._source.search_props.end_time == null) {
                        ctx._source.search_props.end_time = [];
                    }

                    // Collect all end_time values from capture_props
                    // (backward compatibility)
                    if (ctx._source.capture_props != null &&
                        ctx._source.capture_props.end_bound != null) {
                        if (!ctx._source.search_props.end_time.contains(
                            ctx._source.capture_props.end_bound)) {
                            ctx._source.search_props.end_time.add(
                                ctx._source.capture_props.end_bound);
                        }
                    }

                    // Collect all end_time values from channels
                    // (multi-channel support)
                    if (ctx._source.channels != null) {
                        for (channel in ctx._source.channels) {
                            if (channel.channel_props != null &&
                                channel.channel_props.end_bound != null) {
                                if (!ctx._source.search_props.end_time
                                    .contains(channel.channel_props.end_bound)) {
                                    ctx._source.search_props.end_time.add(
                                        channel.channel_props.end_bound);
                                }
                            }
                        }
                    }
                """.strip(),
                "lang": "painless",
            },
            "search_props.span": {
                "source": """
                    if (ctx._source.search_props.span == null) {
                        ctx._source.search_props.span = [];
                    }

                    // Collect all span values from capture_props
                    // (backward compatibility)
                    if (ctx._source.capture_props != null &&
                        ctx._source.capture_props.span != null) {
                        if (!ctx._source.search_props.span.contains(
                            ctx._source.capture_props.span)) {
                            ctx._source.search_props.span.add(
                                ctx._source.capture_props.span);
                        }
                    }

                    // Collect all span values from channels
                    // (multi-channel support)
                    if (ctx._source.channels != null) {
                        for (channel in ctx._source.channels) {
                            if (channel.channel_props != null &&
                                channel.channel_props.span != null) {
                                if (!ctx._source.search_props.span.contains(
                                    channel.channel_props.span)) {
                                    ctx._source.search_props.span.add(
                                        channel.channel_props.span);
                                }
                            }
                        }
                    }
                """.strip(),
                "lang": "painless",
            },
            "search_props.gain": {
                "source": """
                    if (ctx._source.search_props.gain == null) {
                        ctx._source.search_props.gain = [];
                    }

                    // Collect all gain values from capture_props
                    // (backward compatibility)
                    if (ctx._source.capture_props != null &&
                        ctx._source.capture_props.gain != null) {
                        if (!ctx._source.search_props.gain.contains(
                            ctx._source.capture_props.gain)) {
                            ctx._source.search_props.gain.add(
                                ctx._source.capture_props.gain);
                        }
                    }

                    // Collect all gain values from channels
                    // (multi-channel support)
                    if (ctx._source.channels != null) {
                        for (channel in ctx._source.channels) {
                            if (channel.channel_props != null &&
                                channel.channel_props.gain != null) {
                                if (!ctx._source.search_props.gain.contains(
                                    channel.channel_props.gain)) {
                                    ctx._source.search_props.gain.add(
                                        channel.channel_props.gain);
                                }
                            }
                        }
                    }
                """.strip(),
                "lang": "painless",
            },
            "search_props.bandwidth": {
                "source": """
                    if (ctx._source.search_props.bandwidth == null) {
                        ctx._source.search_props.bandwidth = [];
                    }

                    // Collect all bandwidth values from capture_props
                    // (backward compatibility)
                    if (ctx._source.capture_props != null &&
                        ctx._source.capture_props.bandwidth != null) {
                        if (!ctx._source.search_props.bandwidth.contains(
                            ctx._source.capture_props.bandwidth)) {
                            ctx._source.search_props.bandwidth.add(
                                ctx._source.capture_props.bandwidth);
                        }
                    }

                    // Collect all bandwidth values from channels
                    // (multi-channel support)
                    if (ctx._source.channels != null) {
                        for (channel in ctx._source.channels) {
                            if (channel.channel_props != null &&
                                channel.channel_props.bandwidth != null) {
                                if (!ctx._source.search_props.bandwidth
                                    .contains(channel.channel_props.bandwidth)) {
                                    ctx._source.search_props.bandwidth.add(
                                        channel.channel_props.bandwidth);
                                }
                            }
                        }
                    }
                """.strip(),
                "lang": "painless",
            },
            "search_props.sample_rate": {
                "source": """
                    if (ctx._source.search_props.sample_rate == null) {
                        ctx._source.search_props.sample_rate = [];
                    }

                    // Collect all sample_rate values from capture_props
                    // (backward compatibility)
                    if (ctx._source.capture_props != null &&
                        ctx._source.capture_props.sample_rate_numerator
                        != null && ctx._source.capture_props
                        .sample_rate_denominator != null) {
                        double sample_rate = ctx._source.capture_props
                            .sample_rate_numerator / ctx._source.capture_props
                            .sample_rate_denominator;
                        if (!ctx._source.search_props.sample_rate
                            .contains(sample_rate)) {
                            ctx._source.search_props.sample_rate
                                .add(sample_rate);
                        }
                    }

                    // Collect all sample_rate values from channels
                    // (multi-channel support)
                    if (ctx._source.channels != null) {
                        for (channel in ctx._source.channels) {
                            if (channel.channel_props != null &&
                                channel.channel_props.sample_rate_numerator
                                != null && channel.channel_props
                                .sample_rate_denominator != null) {
                                double sample_rate = channel.channel_props
                                    .sample_rate_numerator / channel
                                    .channel_props.sample_rate_denominator;
                                if (!ctx._source.search_props.sample_rate
                                    .contains(sample_rate)) {
                                    ctx._source.search_props.sample_rate
                                        .add(sample_rate);
                                }
                            }
                        }
                    }
                """.strip(),
                "lang": "painless",
            },
        }

    def _init_search_props(
        self,
        index_name: str,
        capture_uuid: str,
    ) -> None:
        """Initialize the search_props field."""
        try:
            log.info(
                f"Initializing search_props for capture '{capture_uuid}'...",
            )

            init_script = {
                "script": {
                    "source": (
                        "if (ctx._source.search_props == null) {"
                        "    ctx._source.search_props = new HashMap();"
                        "}"
                    ),
                    "lang": "painless",
                },
            }

            _response = self.client.update(
                index=index_name,
                id=capture_uuid,
                body=init_script,
            )
            if _response.get("result") != "updated":
                log.error(
                    "Failed to initialize search_props for "
                    f"cap={capture_uuid}: {_response!s}",
                )
        except (RequestError, OpensearchConnectionError) as e:
            log.error(f"Error initializing search_props: {e!s}")

    def get_transform_scripts(self) -> dict[str, dict[str, str]]:
        """Get the transform scripts based on capture type."""
        match self.capture_type:
            case CaptureType.RadioHound:
                return self.rh_field_transforms
            case CaptureType.DigitalRF:
                return self.drf_field_transforms
            case _:
                log.error(
                    f"Unknown capture type: {self.capture_type}",
                )
                return {}

    def apply_field_transforms(self, index_name: str, capture_uuid: str) -> None:
        """Apply transforms for search_props fields.

        Args:
            index_name: Name of the index to apply transforms to
            capture_uuid: UUID of the specific capture to transform.
        """
        # Initialize search_props first
        self._init_search_props(index_name, capture_uuid)

        # refresh the index
        self.client.indices.refresh(index=index_name)

        field_transforms = self.get_transform_scripts()
        log.info(
            f"Got {len(field_transforms)} field transforms for capture type "
            f"{self.capture_type}"
        )

        for field, transform in field_transforms.items():
            try:
                log.info(
                    f"Applying transform for field '{field}'",
                )
                log.info(
                    f"Transform source: {transform['source'][:100]}..."
                )  # Log first 100 chars
                try:
                    _response = self.client.update(
                        index=index_name,
                        id=capture_uuid,
                        body={
                            "script": {
                                "source": transform["source"],
                                "lang": transform["lang"],
                            },
                        },
                    )
                    log.info(f"Update response: {_response}")
                    if _response.get("result") != "updated":
                        log.error(
                            f"Failed to transform field '{field}': {_response!s}",
                        )
                        continue
                    log.info(
                        f"Successfully TRANSFORMED field '{field}'",
                    )
                except (RequestError, OpensearchConnectionError) as e:
                    log.error(f"Error with direct update: {e!s}")
                    log.error(
                        f"Error details: {e.info if hasattr(e, 'info') else ''}"
                        f"No details"
                        if not hasattr(e, "info")
                        else ""
                    )

            except (RequestError, OpensearchConnectionError) as e:
                log.error(
                    f"Error applying transform for field '{field}': {e!s}",
                )
