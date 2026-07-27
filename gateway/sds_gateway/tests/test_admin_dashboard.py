"""Tests for the custom admin dashboard."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import OperationalError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.status import HTTP_200_OK

from sds_gateway.admin import _dashboard_context
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_dashboard_context_empty_database() -> None:
    ctx = _dashboard_context()

    assert ctx["active_file_count"] == 0
    assert ctx["active_total_size"] == "0 B"
    assert ctx["cleanup_file_count"] == 0
    assert ctx["cleanup_total_size"] == "0 B"
    assert list(ctx["top_users"]) == []
    assert ctx["capture_count"] == 0
    assert ctx["dataset_count"] == 0


def test_dashboard_context_with_fixture_data() -> None:
    user = UserFactory()
    now = timezone.now()

    File.objects.create(
        owner=user,
        name="active1.h5",
        size=1024 * 1024,
        directory="files/",
        file="files/active1.h5",
    )
    File.objects.create(
        owner=user,
        name="active2.h5",
        size=2 * 1024 * 1024,
        directory="files/",
        file="files/active2.h5",
    )

    # Deleted file older than 30 days (cleanup candidate)
    File.objects.create(
        owner=user,
        name="old_deleted.h5",
        size=5 * 1024 * 1024,
        directory="files/",
        file="files/old_deleted.h5",
        is_deleted=True,
        deleted_at=now - timedelta(days=45),
    )

    # Deleted file less than 30 days ago (not a cleanup candidate)
    File.objects.create(
        owner=user,
        name="recent_deleted.h5",
        size=3 * 1024 * 1024,
        directory="files/",
        file="files/recent_deleted.h5",
        is_deleted=True,
        deleted_at=now - timedelta(days=5),
    )

    Capture.objects.create(
        name="cap1",
        owner=user,
        capture_type="drf",
        top_level_dir="/data/cap1",
    )
    Capture.objects.create(
        name="cap_deleted",
        owner=user,
        capture_type="drf",
        top_level_dir="/data/cap_deleted",
        is_deleted=True,
    )

    Dataset.objects.create(name="ds1", owner=user)
    Dataset.objects.create(name="ds_deleted", owner=user, is_deleted=True)

    ctx = _dashboard_context()

    active_file_count = 2
    capture_count = 1
    dataset_count = 1
    cleanup_file_count = 1

    assert ctx["active_file_count"] == active_file_count
    assert ctx["capture_count"] == capture_count
    assert ctx["dataset_count"] == dataset_count
    assert ctx["cleanup_file_count"] == cleanup_file_count
    assert ctx["cleanup_total_size"] != "0 B"


def test_cleanup_candidates_exclude_recent_deletes() -> None:
    """Only files deleted >30 days ago appear as cleanup candidates."""
    user = UserFactory()
    now = timezone.now()

    File.objects.create(
        owner=user,
        name="old.h5",
        size=100,
        directory="files/",
        file="files/old.h5",
        is_deleted=True,
        deleted_at=now - timedelta(days=31),
    )
    File.objects.create(
        owner=user,
        name="new.h5",
        size=200,
        directory="files/",
        file="files/new.h5",
        is_deleted=True,
        deleted_at=now - timedelta(days=29),
    )

    ctx = _dashboard_context()

    assert ctx["cleanup_file_count"] == 1


def test_top_users_ordered_by_total_size() -> None:
    user_a = UserFactory()
    user_b = UserFactory()
    user_c = UserFactory()

    # user_b: 3MB, user_a: 1MB, user_c: 0
    File.objects.create(
        owner=user_a,
        name="a.h5",
        size=1024 * 1024,
        directory="files/",
        file="files/a.h5",
    )
    for i in range(3):
        File.objects.create(
            owner=user_b,
            name=f"b{i}.h5",
            size=1024 * 1024,
            directory="files/",
            file=f"files/b{i}.h5",
        )

    ctx = _dashboard_context()
    top_users = list(ctx["top_users"])

    assert top_users[0].email == user_b.email
    assert top_users[1].email == user_a.email
    # user_c has no files, not in the list
    assert all(u.email != user_c.email for u in top_users)


def test_dashboard_context_query_count() -> None:
    """Verify no N+1 queries — dashboard context should use a bounded number."""
    with CaptureQueriesContext(connection) as queries:
        _dashboard_context()

    # Expected queries: active files aggregate, cleanup files aggregate,
    # capture count, dataset count, top users, recent users, superusers,
    # total users, health snapshot = 9
    max_queries = 9
    assert len(queries) <= max_queries


def test_dashboard_index_view_returns_200(client) -> None:
    admin_user = UserFactory(is_staff=True, is_superuser=True)
    client.force_login(admin_user)

    response = client.get(reverse("admin:index"))

    assert response.status_code == HTTP_200_OK
    assert b"Gateway Dashboard" in response.content
    assert b"Files" in response.content
    assert b"Captures" in response.content
    assert b"Datasets" in response.content


def test_dashboard_context_recent_users() -> None:
    """Only users who joined within the last 14 days appear in recent_users."""
    recent = UserFactory(date_joined=timezone.now() - timedelta(days=10))
    old = UserFactory(date_joined=timezone.now() - timedelta(days=20))

    ctx = _dashboard_context()
    recent_emails = [u["email"] for u in ctx["recent_users"]]

    assert recent.email in recent_emails
    assert old.email not in recent_emails


def test_dashboard_context_superusers() -> None:
    """Staff and superuser users appear in the superusers list."""
    staff = UserFactory(is_staff=True, is_superuser=False)
    superuser = UserFactory(is_staff=False, is_superuser=True)
    regular = UserFactory(is_staff=False, is_superuser=False)

    ctx = _dashboard_context()
    su_emails = [u["email"] for u in ctx["superusers"]]

    assert staff.email in su_emails
    assert superuser.email in su_emails
    assert regular.email not in su_emails


def test_dashboard_context_admin_urls() -> None:
    """Admin URL fields are non-empty strings."""
    ctx = _dashboard_context()

    for key in (
        "file_admin_url",
        "capture_admin_url",
        "dataset_admin_url",
        "user_admin_url",
    ):
        assert isinstance(ctx[key], str)
        assert len(ctx[key]) > 0


def test_dashboard_context_db_error_returns_fallback() -> None:
    """When DB queries fail, _dashboard_context returns safe defaults."""
    with patch(
        "sds_gateway.admin.File.objects.filter",
        side_effect=OperationalError("DB connection lost"),
    ):
        ctx = _dashboard_context()

    assert ctx["active_file_count"] == 0
    assert ctx["active_total_size"] == "0 B"
    assert ctx["cleanup_file_count"] == 0
    assert ctx["cleanup_total_size"] == "0 B"
    assert ctx["top_users"] == []
    assert ctx["capture_count"] == 0
    assert ctx["dataset_count"] == 0
    assert ctx["health_payload"] is None
    assert ctx["recent_users"] == []
    assert ctx["superusers"] == []
    assert ctx["total_user_count"] == 0
    assert ctx["file_admin_url"] == "#"
    assert ctx["capture_admin_url"] == "#"
    assert ctx["dataset_admin_url"] == "#"
    assert ctx["user_admin_url"] == "#"
