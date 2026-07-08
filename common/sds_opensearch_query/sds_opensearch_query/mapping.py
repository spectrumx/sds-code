from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def flatten_property_paths(
    properties: Mapping[str, Any],
    *,
    prefix: str = "",
    separator: str = ".",
) -> frozenset[str]:
    """Collect dotted field paths from an OpenSearch ``properties`` mapping."""
    paths: set[str] = set()

    for field, spec in properties.items():
        path = f"{prefix}{separator}{field}" if prefix else field
        if not isinstance(spec, dict):
            paths.add(path)
            continue

        if spec.get("type") == "nested":
            nested_props = spec.get("properties", {})
            if isinstance(nested_props, dict):
                for nested_field in nested_props:
                    paths.add(f"{path}{separator}{nested_field}")
            continue

        if "properties" in spec:
            paths.update(
                flatten_property_paths(
                    spec["properties"],
                    prefix=path,
                    separator=separator,
                ),
            )
            continue

        paths.add(path)

    return frozenset(paths)
