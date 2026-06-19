"""Helpers to keep gateway export serializers aligned with sync Pydantic models."""

from __future__ import annotations

from typing import Any

from rest_framework.serializers import BaseSerializer


def serializer_output_field_names(serializer: BaseSerializer[Any]) -> set[str]:
    return set(serializer.fields.keys())


def assert_field_names_match(
    serializer: BaseSerializer[Any],
    pydantic_model: type,
    *,
    label: str,
) -> None:
    expected = set(pydantic_model.model_fields.keys())
    actual = serializer_output_field_names(serializer)
    if expected != actual:
        missing = expected - actual
        extra = actual - expected
        msg = f"{label} field mismatch: missing={sorted(missing)!r} extra={sorted(extra)!r}"
        raise AssertionError(msg)
