import logging
import tempfile
from pathlib import Path
from typing import Any

from opensearchpy import exceptions as os_exceptions

from sds_gateway.api_methods.helpers.extract_drf_metadata import (
    validate_metadata_by_channel,
)
from sds_gateway.api_methods.helpers.reconstruct_file_tree import find_rh_metadata_file
from sds_gateway.api_methods.helpers.reconstruct_file_tree import reconstruct_tree
from sds_gateway.api_methods.helpers.rh_schema_generator import load_rh_file
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.users.models import User

# Set up logging
logger = logging.getLogger(__name__)


def index_capture_metadata(capture: Capture, capture_props: dict[str, Any]):
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
        logger.info(msg)
    except os_exceptions.ConnectionError as e:
        # Log the error
        msg = f"Failed to connect to OpenSearch: {e}"
        logger.exception(msg)
        # Handle the error (e.g., retry, raise an exception, etc.)
        raise


def handle_metadata(
    capture: Capture,
    top_level_dir: Path,
    capture_type: CaptureType,
    channel: str | None,
    requester: User,
):
    with tempfile.TemporaryDirectory() as temp_dir:
        # Reconstruct the file tree in a temporary directory
        tmp_dir_path, files_to_connect = reconstruct_tree(
            target_dir=Path(temp_dir),
            top_level_dir=top_level_dir,
            owner=requester,
        )

        # Connect the files to the capture
        for cur_file in files_to_connect:
            cur_file.capture = capture
            cur_file.save()

        capture_props = None
        # Validate the metadata and index it
        if capture_type == CaptureType.DigitalRF:
            if channel:
                capture_props = validate_metadata_by_channel(tmp_dir_path, channel)
            else:
                msg = "Channel is required for DigitalRF captures"
                logger.exception(msg)
                raise ValueError(msg)
        elif capture_type == CaptureType.RadioHound:
            rh_metadata_file = find_rh_metadata_file(tmp_dir_path)
            rh_data = load_rh_file(rh_metadata_file)
            capture_props = rh_data.model_dump(mode="json")

        if capture_props:
            index_capture_metadata(capture, capture_props)
        else:
            msg = f"No metadata found for capture '{capture.uuid}'"
            logger.exception(msg)
            raise ValueError(msg)


def retrieve_indexed_metadata(
    capture_or_captures: Capture | list[Any],
    *,
    is_many: bool = False,
) -> dict[str, Any]:
    """Retrieve metadata for one or more captures.

    Args:
        capture_or_captures: Single capture or list of captures to retrieve metadata for
        is_many: If True, this is part of a bulk request and should use mget
    """
    try:
        client = get_opensearch_client()

        if is_many:
            # Raise error if not a list
            if not isinstance(capture_or_captures, list):
                msg = "capture_or_captures must be a list when is_many is True"
                raise ValueError(msg)

            # Build mget body for all captures
            docs = [
                {"_index": capture.index_name, "_id": str(capture.uuid)}
                for capture in capture_or_captures
            ]

            if not docs:
                return {}

            # Use mget to fetch all documents in one request
            response = client.mget(body={"docs": docs})

            # Check that every capture has a corresponding document in the response
            if not all(doc.get("found") for doc in response["docs"]):
                failed_capture_uuids = [
                    doc["_id"] for doc in response["docs"] if not doc.get("found")
                ]
                msg = f"Metadata retrieval failed for captures: {failed_capture_uuids}"
                raise ValueError(msg)

            # For multiple captures, return a dict mapping uuid to capture_props
            return {
                str(capture.uuid): doc.get("_source", {}).get("capture_props", {})
                for capture, doc in zip(
                    capture_or_captures,
                    response["docs"],
                    strict=True,
                )
            }

        response = client.get(
            index=capture_or_captures.index_name,
            id=capture_or_captures.uuid,
        )
        return response["_source"]["capture_props"]
    except os_exceptions.NotFoundError:
        # Log the error
        msg = "Document(s) or index not found in OpenSearch for metadata retrieval"
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
