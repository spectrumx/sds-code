from typing import Any

from loguru import logger as log
from opensearchpy import OpenSearch
from opensearchpy import exceptions as os_exceptions

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.utils.metadata_schemas import get_mapping_by_capture_type
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client


def create_index(
    client: OpenSearch, index_name: str, capture_type: CaptureType
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


def index_capture_metadata(capture: Capture, capture_props: dict[str, Any]) -> None:
    try:
        client = get_opensearch_client()

        if not client.indices.exists(index=capture.index_name):
            msg = f"Unknown index name: {capture.index_name}"
            raise UnknownIndexError(msg)

        document = {
            "capture_type": capture.capture_type,
            "channel": capture.channel,
            "created_at": capture.created_at,
            "is_deleted": capture.is_deleted,
            "deleted_at": capture.deleted_at,
            "scan_group": capture.scan_group,
            "capture_props": capture_props,
        }

        # index capture
        client.index(
            index=capture.index_name,
            id=capture.uuid,
            body=document,
        )
        msg = (
            f"Metadata for capture '{capture.uuid}' indexed in '{capture.index_name}'."
        )
        log.info(msg)
    except os_exceptions.ConnectionError as e:
        msg = f"Failed to connect to OpenSearch: {e}"
        log.exception(msg)
        raise


def retrieve_indexed_metadata(
    capture_or_captures: Capture | list[Capture],
) -> dict[str, Any]:
    """Retrieve metadata for one or more captures from OpenSearch.

    Args:
        capture_or_captures: Single capture or list of captures to retrieve metadata
    Returns:
        dict:   Mapping of capture UUID to its metadata
    """
    try:
        os_client = get_opensearch_client()

        is_many = isinstance(capture_or_captures, list)

        if not is_many:
            if not isinstance(capture_or_captures, Capture):  # pragma: no cover
                msg = "Invalid input type for metadata retrieval"
                raise ValueError(msg)
            response = os_client.get(
                index=capture_or_captures.index_name,
                id=capture_or_captures.uuid,
            )
            return response["_source"]["capture_props"]

        # build mget body for all captures
        docs = [
            {"_index": capture.index_name, "_id": str(capture.uuid)}
            for capture in capture_or_captures
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
                "OpenSearch metadata retrieval failed "
                f"for captures: {failed_capture_uuids}"
            )
            # report error internally, but don't fail the request for a missing document
            log.warning(msg)

        # map capture uuid to its properties
        return {
            str(capture.uuid): doc.get("_source", {}).get("capture_props", {})
            for capture, doc in zip(
                capture_or_captures,
                response["docs"],
                strict=True,
            )
        }

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
