"""Recording stand-in for opensearchpy.OpenSearch in tests."""

from __future__ import annotations

from typing import Any

from opensearchpy.exceptions import NotFoundError


class RecordingOpenSearch:
    def __init__(self) -> None:
        self.index_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self._docs: dict[tuple[str, str], dict[str, Any]] = {}

    def index(self, **kwargs: Any) -> dict[str, str]:
        self.index_calls.append(kwargs)
        self._docs[(kwargs["index"], kwargs["id"])] = dict(kwargs["body"])
        return {"result": "created"}

    def update(self, **kwargs: Any) -> dict[str, str]:
        self.update_calls.append(kwargs)
        index_name = kwargs["index"]
        doc_id = kwargs["id"]
        body = kwargs.get("body") or {}
        existing = self._docs.get((index_name, doc_id), {})
        if "doc" in body:
            existing = {**existing, **body["doc"]}
        if "upsert" in body:
            existing = {**body["upsert"], **existing}
        self._docs[(index_name, doc_id)] = existing
        return {"result": "updated"}

    def get(self, *, index: str, **kwargs: Any) -> dict[str, Any]:
        doc_id_value = kwargs["id"]
        key = (index, doc_id_value)
        if key not in self._docs:
            raise NotFoundError(
                404,
                "index_not_found_exception",
                {"_index": index, "_id": doc_id_value},
            )
        return {"_index": index, "_id": doc_id_value, "_source": self._docs[key]}

    def search(self, *, index: str, body: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        site_name = _site_name_from_search_body(body or {})
        hits: list[dict[str, Any]] = []
        for (doc_index, doc_id), source in self._docs.items():
            if doc_index != index:
                continue
            if site_name is not None and source.get("site_name") != site_name:
                continue
            hits.append({"_index": doc_index, "_id": doc_id, "_source": source})
        return {"hits": {"hits": hits, "total": {"value": len(hits)}}}

    def ping(self) -> bool:
        return True


def _site_name_from_search_body(body: dict[str, Any]) -> str | None:
    query = body.get("query") or {}
    bool_q = query.get("bool") or {}
    for clause in bool_q.get("should") or []:
        if not isinstance(clause, dict):
            continue
        term = clause.get("term") or {}
        if "site_name.keyword" in term:
            return str(term["site_name.keyword"])
        if "site_name" in term:
            return str(term["site_name"])
    term = query.get("term") or {}
    if "site_name.keyword" in term:
        return str(term["site_name.keyword"])
    if "site_name" in term:
        return str(term["site_name"])
    return None
