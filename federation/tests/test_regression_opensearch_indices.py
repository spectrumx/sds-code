"""Regression: OpenSearch fed-* mappings include RFC §6 search fields."""

from __future__ import annotations

import pytest
from sds_federation.schemas.opensearch_indices import RFC_FED_CAPTURE_PROPERTIES
from sds_federation.schemas.opensearch_indices import RFC_FED_DATASET_PROPERTIES
from sds_federation.schemas.opensearch_indices import fed_capture_mappings
from sds_federation.schemas.opensearch_indices import fed_dataset_mappings

RFC_DATASET_FIELDS = frozenset(
    {
        "uuid",
        "site_name",
        "name",
        "description",
        "abstract",
        "keywords",
        "owner_name",
        "created_at",
        "updated_at",
        "size",
        "capture_count",
        "url",
    },
)

RFC_CAPTURE_FIELDS = frozenset(
    {
        "uuid",
        "site_name",
        "capture_type",
        "channel",
        "center_frequency",
        "sample_rate",
        "start_time",
        "end_time",
        "dataset_ids",
        "url",
    },
)


@pytest.mark.regression
def test_rfc_dataset_fields_explicit_in_mapping() -> None:
    assert set(RFC_FED_DATASET_PROPERTIES) == RFC_DATASET_FIELDS
    props = fed_dataset_mappings()["properties"]
    assert set(props) == RFC_DATASET_FIELDS


@pytest.mark.regression
def test_rfc_capture_fields_explicit_in_mapping() -> None:
    assert set(RFC_FED_CAPTURE_PROPERTIES) == RFC_CAPTURE_FIELDS
    props = fed_capture_mappings()["properties"]
    assert set(props) == RFC_CAPTURE_FIELDS


@pytest.mark.regression
def test_fed_mappings_allow_dynamic_extra_fields() -> None:
    assert fed_dataset_mappings()["dynamic"] is True
    assert fed_capture_mappings()["dynamic"] is True
