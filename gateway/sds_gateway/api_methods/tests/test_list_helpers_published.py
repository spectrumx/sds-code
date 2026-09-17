"""Tests for published local asset list query helpers."""

from __future__ import annotations

import pytest

from sds_gateway.api_methods.helpers.list_helpers import get_published_captures
from sds_gateway.api_methods.helpers.list_helpers import get_published_datasets
from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.tests.factories import CaptureFactory
from sds_gateway.api_methods.tests.factories import DatasetFactory

pytestmark = pytest.mark.django_db


def test_get_published_captures_requires_final_public_dataset() -> None:
    draft_public = DatasetFactory(
        status=DatasetStatus.DRAFT,
        is_public=True,
        is_deleted=False,
    )
    capture_on_draft = CaptureFactory(is_deleted=False)
    capture_on_draft.datasets.add(draft_public)

    final_public = DatasetFactory(
        status=DatasetStatus.FINAL,
        is_public=True,
        is_deleted=False,
    )
    capture_on_final = CaptureFactory(is_deleted=False)
    capture_on_final.datasets.add(final_public)

    published_uuids = set(get_published_captures().values_list("uuid", flat=True))
    assert capture_on_draft.uuid not in published_uuids
    assert capture_on_final.uuid in published_uuids


def test_get_published_datasets_and_captures_align_on_exportable_criteria() -> None:
    exportable = DatasetFactory(
        status=DatasetStatus.FINAL,
        is_public=True,
        is_deleted=False,
    )
    capture = CaptureFactory(is_deleted=False)
    capture.datasets.add(exportable)

    assert get_published_datasets().filter(uuid=exportable.uuid).exists()
    assert get_published_captures().filter(uuid=capture.uuid).exists()
