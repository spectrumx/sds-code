"""User utilities module."""

import importlib
from typing import Any


def get_index_name_for_capture_type(capture_type: Any) -> str:
    """Get index name for a capture type, avoiding circular imports."""
    # Use dynamic import to avoid circular dependency
    module = importlib.import_module("sds_gateway.api_methods.utils.metadata_schemas")
    infer_index_name = module.infer_index_name

    return infer_index_name(capture_type)
