"""Recording stand-in for opensearchpy.OpenSearch in tests."""

from __future__ import annotations

from typing import Any


class RecordingOpenSearch:
    def __init__(self) -> None:
        self.index_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []

    def index(self, **kwargs: Any) -> dict[str, str]:
        self.index_calls.append(kwargs)
        return {"result": "created"}

    def update(self, **kwargs: Any) -> dict[str, str]:
        self.update_calls.append(kwargs)
        return {"result": "updated"}
