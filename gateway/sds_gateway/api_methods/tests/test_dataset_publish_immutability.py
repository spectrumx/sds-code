"""Tests for Dataset publish immutability (status final / is_public)."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.tests.factories import DatasetFactory

pytestmark = pytest.mark.django_db


class TestDatasetPublishImmutability:
    def test_cannot_revert_final_to_draft(self) -> None:
        dataset = DatasetFactory(status=DatasetStatus.FINAL, is_public=False)
        dataset.status = DatasetStatus.DRAFT
        with pytest.raises(ValidationError, match="cannot be reverted to draft"):
            dataset.save()

    def test_cannot_make_public_dataset_private(self) -> None:
        dataset = DatasetFactory(status=DatasetStatus.DRAFT, is_public=True)
        dataset.is_public = False
        with pytest.raises(ValidationError, match="cannot be reverted to private"):
            dataset.save()

    def test_final_and_public_can_update_other_fields(self) -> None:
        dataset = DatasetFactory(
            status=DatasetStatus.FINAL,
            is_public=True,
            name="Original",
        )
        dataset.name = "Updated title"
        dataset.save()
        dataset.refresh_from_db()
        assert dataset.name == "Updated title"
        assert dataset.status == DatasetStatus.FINAL
        assert dataset.is_public is True

    def test_draft_can_still_become_final(self) -> None:
        dataset = DatasetFactory(status=DatasetStatus.DRAFT, is_public=False)
        dataset.status = DatasetStatus.FINAL
        dataset.save()
        dataset.refresh_from_db()
        assert dataset.status == DatasetStatus.FINAL
