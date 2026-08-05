"""Regression: ensure_fed_indices creates both fed-* indices."""

from __future__ import annotations

from typing import Any

import pytest
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.services.fed_index import ensure_fed_indices


class _IndicesStub:
    def __init__(self) -> None:
        self.existing: set[str] = set()
        self.create_calls: list[dict[str, Any]] = []

    def exists(self, *, index: str, **kwargs: Any) -> bool:
        return index in self.existing

    def create(self, *, index: str, body: dict[str, Any], **kwargs: Any) -> dict:
        self.create_calls.append({"index": index, "body": body})
        self.existing.add(index)
        return {"acknowledged": True}


class _ClientStub:
    def __init__(self) -> None:
        self.indices = _IndicesStub()


@pytest.mark.regression
def test_ensure_fed_indices_creates_missing_indices() -> None:
    client = _ClientStub()
    ensure_fed_indices(client)  # type: ignore[arg-type]
    names = {c["index"] for c in client.indices.create_calls}
    assert names == {
        AssetTypeEnum.DATASET.index_name,
        AssetTypeEnum.CAPTURE.index_name,
    }
