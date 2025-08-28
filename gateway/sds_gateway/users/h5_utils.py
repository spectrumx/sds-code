"""
HDF5 utility functions for processing and summarizing HDF5 file structures.

This module provides utilities for safely reading and summarizing HDF5 files
for preview purposes, with built-in limits to prevent excessive memory usage.
"""

import logging
from typing import Any

import h5py

logger = logging.getLogger(__name__)


def summarize_h5_group(
    group_obj: h5py.Group,
    depth: int,
    max_children: int = 200,
    max_recursion_depth: int = 4,
) -> dict[str, Any]:
    """
    Summarize an HDF5 group by extracting its attributes and children.

    Args:
        group_obj: HDF5 Group object to summarize
        depth: Current recursion depth
        max_children: Maximum number of children to process per group
        max_recursion_depth: Maximum recursion depth to prevent infinite loops

    Returns:
        Dict containing group type, attributes, and children summary
    """
    children: dict[str, dict] = {}
    for index, (child_name, child) in enumerate(group_obj.items()):
        key = str(child_name)
        children[key] = summarize_h5_object(key, child, depth + 1, max_recursion_depth)
        if index + 1 >= max_children:
            break

    return {
        "type": "group",
        "attributes": {k: str(v) for k, v in group_obj.attrs.items()},
        "children": children,
    }


def summarize_h5_dataset(
    dataset_obj: h5py.Dataset, max_preview_elements: int = 10
) -> dict[str, Any]:
    """
    Summarize an HDF5 dataset by extracting its metadata and optionally a data preview.

    Args:
        dataset_obj: HDF5 Dataset object to summarize
        max_preview_elements: Maximum number of elements to include in preview

    Returns:
        Dict containing dataset type, shape, dtype, attributes, and optional preview
    """
    info = {
        "type": "dataset",
        "shape": [int(x) for x in dataset_obj.shape]
        if hasattr(dataset_obj, "shape")
        else [],
        "dtype": str(dataset_obj.dtype) if hasattr(dataset_obj, "dtype") else "",
        "attributes": {k: str(v) for k, v in dataset_obj.attrs.items()},
    }

    try:
        size = int(dataset_obj.size) if hasattr(dataset_obj, "size") else 0
        if size and size <= max_preview_elements:
            data = dataset_obj[()]
            if hasattr(data, "tolist"):
                data = data.tolist()
            if isinstance(data, (bytes, bytearray)):
                try:
                    data = data.decode("utf-8", errors="replace")
                except Exception:  # noqa: BLE001 - best-effort decoding
                    data = str(data)
            info["preview"] = data
    except Exception as exc:  # noqa: BLE001 - preview is best-effort
        logger.debug("H5 dataset preview skipped: %s", exc)

    return info


def summarize_h5_object(
    name: str,
    obj: h5py.Group | h5py.Dataset,
    depth: int = 0,
    max_recursion_depth: int = 4,
) -> dict[str, Any]:
    """
    Summarize any HDF5 object (group or dataset) recursively.

    Args:
        name: Name of the HDF5 object
        obj: HDF5 object (Group or Dataset) to summarize
        depth: Current recursion depth
        max_recursion_depth: Maximum recursion depth to prevent infinite loops

    Returns:
        Dict containing object summary
    """
    if depth > max_recursion_depth:
        return {"type": "group", "attributes": {}, "children": {}}

    if isinstance(obj, h5py.Group):
        return summarize_h5_group(obj, depth, max_recursion_depth=max_recursion_depth)
    if isinstance(obj, h5py.Dataset):
        return summarize_h5_dataset(obj)
    return {"type": "unknown"}


def sanitize_h5_data(value: Any) -> Any:
    """
    Recursively sanitize HDF5 data by converting bytes to strings and ensuring
    JSON serializable format.

    Args:
        value: Any value that might contain bytes, nested dicts, or lists

    Returns:
        Sanitized value with bytes converted to strings
    """
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - best-effort decoding
            return str(value)
    elif isinstance(value, dict):
        return {str(k): sanitize_h5_data(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [sanitize_h5_data(v) for v in value]
    else:
        return value


def summarize_h5_file(
    h5_file: h5py.File,
    max_children_per_group: int = 200,
    max_recursion_depth: int = 4,
    max_preview_elements: int = 10,
) -> dict[str, Any]:
    """
    Create a complete summary of an HDF5 file structure.

    Args:
        h5_file: Open HDF5 file object
        max_children_per_group: Maximum children to process per group
        max_recursion_depth: Maximum recursion depth
        max_preview_elements: Maximum elements to include in dataset previews

    Returns:
        Dict containing the complete file structure summary
    """
    structure = {}
    for key, obj in h5_file.items():
        structure[str(key)] = summarize_h5_object(
            str(key), obj, depth=0, max_recursion_depth=max_recursion_depth
        )

    # Sanitize the entire structure
    return sanitize_h5_data(structure)
