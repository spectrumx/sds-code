from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from collections.abc import Callable


def nested_query_clause(
    field_path: str,
    query_type: str,
    value: Any,
    *,
    levels_nested: int | None = None,
    last_path: str | None = None,
) -> dict[str, Any]:
    """Build a nested OpenSearch clause for a dotted field path."""
    if levels_nested is None:
        levels_nested = field_path.count(".")

    if levels_nested == 0:
        key = f"{last_path}.{field_path}" if last_path else field_path
        return {query_type: {key: value}}

    path_parts = field_path.split(".")
    current_path = path_parts[0]
    if last_path is not None:
        current_path = f"{last_path}.{current_path}"

    return {
        "nested": {
            "path": current_path,
            "query": nested_query_clause(
                field_path=".".join(path_parts[1:]),
                query_type=query_type,
                value=value,
                levels_nested=levels_nested - 1,
                last_path=current_path,
            ),
        },
    }


def build_metadata_filter_clauses(
    metadata_filters: list[dict[str, Any]] | None,
    *,
    known_field_paths: frozenset[str] | None = None,
    on_unknown_field: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Turn API metadata filter dicts into OpenSearch query clauses."""
    if not metadata_filters:
        return []

    clauses: list[dict[str, Any]] = []
    for query in metadata_filters:
        field_path: str = query["field_path"]
        query_type: str = query["query_type"]
        filter_value: Any = query["filter_value"]

        if known_field_paths is not None and field_path not in known_field_paths:
            if on_unknown_field is not None:
                on_unknown_field(field_path)

        levels_nested = field_path.count(".")
        if levels_nested > 0:
            clauses.append(
                nested_query_clause(
                    field_path=field_path,
                    query_type=query_type,
                    value=filter_value,
                    levels_nested=levels_nested,
                ),
            )
        else:
            clauses.append({query_type: {field_path: filter_value}})

    return clauses
