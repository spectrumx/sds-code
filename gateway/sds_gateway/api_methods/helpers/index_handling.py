import logging

from opensearchpy import exceptions as os_exceptions

from sds_gateway.api_methods.utils.metadata_schemas import (
    capture_metadata_fields_by_type as md_props_by_type,
)
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client

# Set up logging
logger = logging.getLogger(__name__)


def create_index(client, index_name, capture_type):
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
                    "metadata": {
                        "type": "object",
                        "properties": md_props_by_type[capture_type]["index_mapping"],
                    },
                },
            },
        }
        client.indices.create(index=index_name, body=index_body)
        msg = f"Index '{index_name}' created."
        logger.info(msg)
    except Exception as e:
        msg = f"Failed to create index '{index_name}': {e}"
        logger.exception(msg)
        raise


def index_capture_metadata(capture, metadata):
    try:
        client = get_opensearch_client()

        # Create the index if it does not exist
        if not client.indices.exists(index=capture.index_name):
            create_index(client, capture.index_name, capture.capture_type)

        # Combine capture fields and additional fields
        document = {
            "channel": capture.channel,
            "capture_type": capture.capture_type,
            "created_at": capture.created_at,
            "metadata": metadata,
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
        logger.info(msg)
    except os_exceptions.ConnectionError as e:
        # Log the error
        msg = f"Failed to connect to OpenSearch: {e}"
        logger.exception(msg)
        # Handle the error (e.g., retry, raise an exception, etc.)
        raise


def retrieve_indexed_metadata(capture_or_captures, *, is_many: bool = False):
    """Retrieve metadata for one or more captures.

    Args:
        capture_or_captures: Single capture or list of captures to retrieve metadata for
        is_many: If True, this is part of a bulk request and should use mget
    """
    try:
        client = get_opensearch_client()

        if is_many:
            if not isinstance(capture_or_captures, list):
                capture_or_captures = [capture_or_captures]

            # Build mget body for all captures
            docs = [
                {"_index": capture.index_name, "_id": str(capture.uuid)}
                for capture in capture_or_captures
            ]

            if not docs:
                return {}

            # Use mget to fetch all documents in one request
            response = client.mget(body={"docs": docs})

            # If single capture was passed, return its metadata
            if not isinstance(capture_or_captures, list):
                doc = response["docs"][0]
                return (
                    doc.get("_source", {}).get("metadata", {})
                    if doc.get("found")
                    else {}
                )

            # For multiple captures, return a dict mapping uuid to metadata
            return {
                str(capture.uuid): doc.get("_source", {}).get("metadata", {})
                for capture, doc in zip(
                    capture_or_captures,
                    response["docs"],
                    strict=False,
                )
                if doc.get("found")
            }

        response = client.get(
            index=capture_or_captures.index_name,
            id=capture_or_captures.uuid,
        )
        return response["_source"]["metadata"]
    except os_exceptions.NotFoundError:
        # Log the error
        msg = "Document or index not found in OpenSearch for metadata retrieval"
        logger.warning(msg)
        # Return an empty dictionary
        return {}
    except os_exceptions.ConnectionError as e:
        # Log the error
        msg = f"Failed to connect to OpenSearch: {e}"
        logger.exception(msg)
        # Handle the error (e.g., retry, raise an exception, etc.)
        raise
    except os_exceptions.RequestError as e:
        msg = f"OpenSearch query error: {e}"
        logger.exception(msg)
        raise
    except os_exceptions.OpenSearchException as e:
        msg = f"OpenSearch error: {e}"
        logger.exception(msg)
        raise
