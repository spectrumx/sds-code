from typing import Any
from typing import cast

from loguru import logger as log
from opensearchpy import OpenSearch
from opensearchpy import exceptions as os_exceptions

from sds_gateway.api_methods.helpers.transforms import Transforms
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.utils.metadata_schemas import base_properties
from sds_gateway.api_methods.utils.metadata_schemas import get_mapping_by_capture_type
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client


def create_index(
    client: OpenSearch,
    index_name: str,
    capture_type: CaptureType,
) -> None:
    try:
        # Define the index settings and mappings
        index_body = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
            "mappings": get_mapping_by_capture_type(capture_type),
        }
        client.indices.create(index=index_name, body=index_body)
        msg = f"Index '{index_name}' created."
        log.info(msg)
    except Exception as e:
        msg = f"Failed to create index '{index_name}': {e}"
        log.exception(msg)
        raise


class UnknownIndexError(Exception):
    pass


def index_capture_metadata(
    capture: Capture,
    capture_props: dict[str, Any],
    channel_metadata: dict[str, dict[str, Any]] | None = None,
) -> None:
    try:
        client = get_opensearch_client()

        if not client.indices.exists(index=capture.index_name):
            msg = f"Unknown index name: {capture.index_name}"
            raise UnknownIndexError(msg)

        document = {
            base_prop: getattr(capture, base_prop) for base_prop in base_properties
        }

        # For DRF captures, create channels structure
        if capture.capture_type == CaptureType.DigitalRF:
            document["channels"] = capture.channels

            # Create channel-specific documents if channels exist
            if capture.channels:
                channels_data = []
                for channel_name in capture.channels:
                    # Use channel-specific metadata if available,
                    # otherwise use capture_props
                    channel_props = (
                        channel_metadata.get(channel_name, capture_props)
                        if channel_metadata
                        else capture_props
                    )

                    channel_doc = {
                        "channel_name": channel_name,
                        "channel_props": channel_props,
                    }
                    channels_data.append(channel_doc)

                document["channels"] = channels_data
        else:
            # For non-DRF captures, use the traditional capture_props
            document["capture_props"] = capture_props

        # index capture
        client.index(
            index=capture.index_name,
            id=capture.uuid,
            body=document,
        )

        # apply field transforms to create search_props fields
        Transforms(capture.capture_type).apply_field_transforms(
            index_name=capture.index_name,
            capture_uuid=str(capture.uuid),
        )

        msg = (
            f"Metadata for capture '{capture.uuid}' indexed in '{capture.index_name}'."
        )
        log.info(msg)
    except os_exceptions.ConnectionError as e:
        msg = f"Failed to connect to OpenSearch: {e}"
        log.exception(msg)
        raise


def _process_single_capture_metadata(
    capture: Capture,
    os_client: OpenSearch,
) -> dict[str, Any]:
    """Process metadata for a single capture."""
    if not isinstance(capture, Capture):  # pragma: no cover
        msg = "Invalid input type for metadata retrieval"
        raise TypeError(msg)

    response = os_client.get(
        index=capture.index_name,
        id=capture.uuid,
    )
    source = response["_source"]

    # For DRF captures, return channels structure
    if capture.capture_type == CaptureType.DigitalRF:
        return source.get("channels", [])
    return source.get("capture_props", {})


def _process_multiple_captures_metadata(
    captures: list[Capture],
    os_client: OpenSearch,
) -> dict[str, Any]:
    """Process metadata for multiple captures."""
    # build mget body for all captures
    docs = [
        {"_index": capture.index_name, "_id": str(capture.uuid)} for capture in captures
    ]

    if not docs:
        log.warning("No captures to retrieve metadata for")
        return {}

    response = os_client.mget(body={"docs": docs})

    # check that every capture has a corresponding document in the response
    if not all(doc.get("found") for doc in response["docs"]):
        failed_capture_uuids = [
            doc["_id"] for doc in response["docs"] if not doc.get("found")
        ]
        msg = (
            f"OpenSearch metadata retrieval failed for captures: {failed_capture_uuids}"
        )
        # report error internally, but don't fail the request for a missing document
        log.warning(msg)

    # map capture uuid to its properties
    result = {}
    for capture, doc in zip(
        captures,
        response["docs"],
        strict=True,
    ):
        source = doc.get("_source", {})

        # For DRF captures, return channels structure
        if capture.capture_type == CaptureType.DigitalRF:
            result[str(capture.uuid)] = source.get("channels", [])
        else:
            result[str(capture.uuid)] = source.get("capture_props", {})
    return result


def retrieve_indexed_metadata(
    capture_or_captures: Capture | list[Capture],
) -> dict[str, Any]:
    """Retrieve metadata for one or more captures from OpenSearch.

    Args:
        capture_or_captures: Single capture or list of captures to retrieve metadata
    Returns:
        dict: Mapping of capture UUID to its metadata (channels for DRF,
            capture_props for others)
    """
    try:
        os_client = get_opensearch_client()

        is_many = isinstance(capture_or_captures, list)

        if not is_many:
            return _process_single_capture_metadata(
                cast("Capture", capture_or_captures), os_client
            )

        return _process_multiple_captures_metadata(
            cast("list[Capture]", capture_or_captures), os_client
        )

    except os_exceptions.NotFoundError:
        # Log the error
        msg = "Document(s) or index not found in OpenSearch for metadata retrieval"
        log.warning(msg)
        # Return an empty dictionary
        return {}
    except os_exceptions.ConnectionError as e:
        # Log the error
        msg = f"Failed to connect to OpenSearch: {e}"
        log.exception(msg)
        # Handle the error (e.g., retry, raise an exception, etc.)
        raise
    except os_exceptions.RequestError as e:
        msg = f"OpenSearch query error: {e}"
        log.exception(msg)
        raise
    except os_exceptions.OpenSearchException as e:
        msg = f"OpenSearch error: {e}"
        log.exception(msg)
        raise
