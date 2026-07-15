from __future__ import annotations

from typing import Any

from opensearchpy import OpenSearch
from opensearchpy import exceptions as os_exceptions

DEFAULT_SEARCH_SIZE = 10_000


def term_clause(field: str, value: Any) -> dict[str, Any]:
    return {"term": {field: value}}


def multi_match_clause(
    query: str,
    fields: list[str],
    *,
    match_type: str = "best_fields",
) -> dict[str, Any]:
    return {
        "multi_match": {
            "query": query,
            "fields": fields,
            "type": match_type,
        },
    }


def federation_not_deleted_clause() -> dict[str, Any]:
    return {"term": {"is_deleted": False}}


def bool_must_search_body(
    *must_clauses: dict[str, Any],
    source_includes: list[str] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "query": {
            "bool": {
                "must": list(must_clauses),
            },
        },
    }
    if source_includes is not None:
        body["_source"] = {"includes": source_includes}
    return body


def _request_error_message(err: os_exceptions.RequestError) -> str:
    info = err.info
    if isinstance(info, dict):
        root_causes: list[dict[str, str]] = info.get("error", {}).get(
            "root_cause",
            [],
        )
        root_cause_reason = root_causes[0].get("reason", "") if root_causes else ""
        reason = str(root_cause_reason) if root_cause_reason else str(info)
    else:
        reason = str(info)
    return f"Query error: {reason}"


def run_search(
    client: OpenSearch,
    *,
    index: str,
    body: dict[str, Any],
    size: int = DEFAULT_SEARCH_SIZE,
) -> list[dict[str, Any]]:
    """Run a search and return raw hit dicts. Raises ValueError for client errors."""
    try:
        response = client.search(
            index=index,
            body=body,
            size=size,  # pyright: ignore[reportCallIssue]
        )
    except os_exceptions.NotFoundError as err:
        msg = f"Index '{index}' not found"
        raise ValueError(msg) from err
    except os_exceptions.ConnectionError:
        raise
    except os_exceptions.RequestError as err:
        raise ValueError(_request_error_message(err)) from err
    except os_exceptions.OpenSearchException:
        raise

    return list(response["hits"]["hits"])
