import logging

from sds_gateway.api_methods.utils.metadata_schemas import drf_capture_metadata_schema
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client

# Set up logging
logger = logging.getLogger(__name__)


def create_drf_index(client, index_name):
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
                        "properties": drf_capture_metadata_schema["index_mapping"],
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
            create_drf_index(client, capture.index_name)

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
    except ConnectionError as e:
        # Log the error
        msg = f"Failed to connect to OpenSearch: {e}"
        logger.exception(msg)
        # Handle the error (e.g., retry, raise an exception, etc.)
        raise


def retrieve_indexed_metadata(capture):
    try:
        client = get_opensearch_client()

        # Retrieve the indexed document
        response = client.get(index=capture.index_name, id=capture.uuid)

        # Retrieve the metadata from the indexed document
        return response["_source"]["metadata"]
    except ConnectionError as e:
        # Log the error
        msg = f"Failed to connect to OpenSearch: {e}"
        logger.exception(msg)
        # Handle the error (e.g., retry, raise an exception, etc.)
        raise
    except Exception as e:
        # Log the error
        msg = f"Failed to retrieve indexed metadata for capture '{capture.uuid}': {e}"
        logger.exception(msg)
        # Handle the error (e.g., retry, raise an exception, etc.)
        raise
