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

    def ping(self) -> bool:
        return True
