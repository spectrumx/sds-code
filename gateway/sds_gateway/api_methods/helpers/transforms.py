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
                    "source": """
                    if (ctx._source.search_props == null) {
                        ctx._source.search_props = new HashMap();
                    }
                    """.strip(),
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

        for field, transform in field_transforms.items():
            try:
                log.info(
                    f"Applying transform for field '{field}'",
                )
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

            except (RequestError, OpensearchConnectionError) as e:
                log.error(
                    f"Error applying transform for field '{field}': {e!s}",
                )
