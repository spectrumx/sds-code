"""Tests for capture reindex candidate discovery."""

import pytest

from sds_gateway.api_methods.helpers.capture_reindex_preview import (
    classify_reindex_candidates,
)
from sds_gateway.api_methods.tests.factories import CaptureFactory
from sds_gateway.api_methods.tests.factories import FileFactory
from sds_gateway.users.tests.factories import UserFactory


@pytest.mark.django_db
class TestClassifyReindexCandidates:
    def test_not_linked_file(self) -> None:
        user = UserFactory()
        capture = CaptureFactory(owner=user)
        directory = f"/files/{user.email}/cap_a"
        linked = FileFactory(owner=user, directory=directory, name="linked.h5")
        linked.captures.add(capture)
        unlinked = FileFactory(
            owner=user,
            directory=directory,
            name="new_rf.h5",
        )
        result = classify_reindex_candidates([unlinked], [linked])
        assert len(result) == 1
        assert result[0]["status"] == "not_linked"
        assert result[0]["uuid"] == str(unlinked.uuid)

    def test_updated_checksum_same_path(self) -> None:
        user = UserFactory()
        capture = CaptureFactory(owner=user)
        directory = f"/files/{user.email}/cap_a"
        old = FileFactory(
            owner=user,
            directory=directory,
            name="rf@1.h5",
            sum_blake3="aaa",
        )
        old.captures.add(capture)
        new = FileFactory(
            owner=user,
            directory=directory,
            name="rf@1.h5",
            sum_blake3="bbb",
        )
        result = classify_reindex_candidates([new], [old])
        assert len(result) == 1
        assert result[0]["status"] == "updated"
        assert result[0]["uuid"] == str(new.uuid)

    def test_unchanged_linked_file_excluded(self) -> None:
        user = UserFactory()
        capture = CaptureFactory(owner=user)
        directory = f"/files/{user.email}/cap_a"
        linked = FileFactory(
            owner=user,
            directory=directory,
            name="rf@1.h5",
            sum_blake3="same",
        )
        linked.captures.add(capture)
        result = classify_reindex_candidates([linked], [linked])
        assert result == []
