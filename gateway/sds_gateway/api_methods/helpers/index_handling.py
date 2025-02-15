from typing import Any

from loguru import logger as log
from opensearchpy import OpenSearch
from opensearchpy import exceptions as os_exceptions

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.utils.metadata_schemas import (
    capture_index_mapping_by_type as md_props_by_type,
)
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client


def create_index(client: OpenSearch, index_name: str, capture_type: str):
    try:
        # Define the index settings and mappings
        index_body = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
            "mappings": {
                "properties": {
                    "channel": {"type": "keyword"},
                    "capture_type": {"type": "keyword"},
                    "created_at": {"type": "date"},
                    "capture_props": {
                        "type": "nested",
                        "properties": md_props_by_type[capture_type],
                    },
                },
            },
        }
        client.indices.create(index=index_name, body=index_body)
        msg = f"Index '{index_name}' created."
        log.info(msg)
    except Exception as e:
        msg = f"Failed to create index '{index_name}': {e}"
        log.exception(msg)
        raise


def index_capture_metadata(capture: Capture, capture_props: dict[str, Any]) -> None:
    try:
        client = get_opensearch_client()

        # Create the index if it does not exist
        if not client.indices.exists(index=capture.index_name):
            msg = f"Index {capture.index_name} not found"
            raise ValueError(msg)

        # Combine capture fields and additional fields
        document = {
            "channel": capture.channel,
            "capture_type": capture.capture_type,
            "created_at": capture.created_at,
            "capture_props": capture_props,
        }

        # Index the document in OpenSearch
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
        # Log the error
        msg = f"Failed to connect to OpenSearch: {e}"
        log.exception(msg)
        # Handle the error (e.g., retry, raise an exception, etc.)
        raise


def retrieve_indexed_metadata(
    capture_or_captures: Capture | list[Capture],
) -> dict[str, Any]:
    """Retrieve metadata for one or more captures.

    Args:
        capture_or_captures: Single capture or list of captures to retrieve metadata
    """
    try:
        client = get_opensearch_client()

        is_many = isinstance(capture_or_captures, list)

        if not is_many:
            if not isinstance(capture_or_captures, Capture):  # pragma: no cover
                msg = "Invalid input type for metadata retrieval"
                raise ValueError(msg)
            response = client.get(
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

        response = client.mget(body={"docs": docs})

        # check that every capture has a corresponding document in the response
        if not all(doc.get("found") for doc in response["docs"]):
            failed_capture_uuids = [
                doc["_id"] for doc in response["docs"] if not doc.get("found")
            ]
            msg = f"Metadata retrieval failed for captures: {failed_capture_uuids}"
            raise ValueError(msg)

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
