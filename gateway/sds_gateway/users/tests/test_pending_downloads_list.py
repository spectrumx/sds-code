"""Tests for the pending downloads list page."""

from datetime import timedelta
from http import HTTPStatus

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from sds_gateway.api_methods.models import TemporaryZipFile
from sds_gateway.api_methods.models import ZipFileStatus
from sds_gateway.users.models import User
from sds_gateway.users.tests.factories import UserFactory
from sds_gateway.users.views.downloads import DownloadsListView
from sds_gateway.users.views.downloads import get_download_display_status

pytestmark = pytest.mark.django_db
DOWNLOADABLE_STATUS_COUNT = 2


def create_download(
    owner: User,
    filename: str,
    *,
    creation_status: str = ZipFileStatus.Created,
    is_downloaded: bool = False,
    expires_at=None,
    created_at=None,
    is_deleted: bool = False,
) -> TemporaryZipFile:
    """Create a temporary download with convenient lifecycle defaults."""
    now = timezone.now()
    download = TemporaryZipFile.objects.create(
        owner=owner,
        file_path=filename,
        filename=filename,
        file_size=1024,
        files_processed=1,
        creation_status=creation_status,
        expires_at=expires_at or now + timedelta(days=1),
        is_downloaded=is_downloaded,
        downloaded_at=now if is_downloaded else None,
        is_deleted=is_deleted,
    )
    if created_at is not None:
        TemporaryZipFile.objects.filter(pk=download.pk).update(created_at=created_at)
        download.refresh_from_db()
    return download


@pytest.fixture
def user() -> User:
    return UserFactory()


@pytest.fixture
def authenticated_client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def test_anonymous_user_is_redirected() -> None:
    response = Client().get(reverse("users:downloads-list"))

    assert response.status_code == HTTPStatus.FOUND
    assert reverse("auth0_login") in response["Location"]


def test_list_only_contains_current_users_non_deleted_downloads(
    authenticated_client: Client,
    user: User,
) -> None:
    visible = create_download(user, "visible.zip")
    create_download(user, "deleted.zip", is_deleted=True)
    create_download(UserFactory(), "other-user.zip")

    response = authenticated_client.get(reverse("users:downloads-list"))

    assert response.status_code == HTTPStatus.OK
    rows = list(response.context["page_obj"])
    assert [row["filename"] for row in rows] == [visible.filename]
    assert reverse("users:downloads-list") in response.content.decode()


def test_display_statuses_follow_requirements_precedence(user: User) -> None:
    now = timezone.now()
    cases = [
        (
            create_download(
                user,
                "pending.zip",
                creation_status=ZipFileStatus.Pending,
                is_downloaded=True,
                expires_at=now + timedelta(hours=1),
            ),
            "Pending",
        ),
        (create_download(user, "ready.zip"), "Ready"),
        (
            create_download(
                user,
                "downloaded.zip",
                is_downloaded=True,
                expires_at=now + timedelta(hours=1),
            ),
            "Downloaded",
        ),
        (
            create_download(
                user,
                "failed.zip",
                creation_status=ZipFileStatus.Failed,
                expires_at=now + timedelta(hours=1),
            ),
            "Failed",
        ),
        (
            create_download(
                user,
                "expired.zip",
                expires_at=now - timedelta(hours=1),
            ),
            "Expired",
        ),
    ]

    assert [get_download_display_status(download) for download, _status in cases] == [
        status for _download, status in cases
    ]


def test_status_and_date_filters_are_applied(
    authenticated_client: Client,
    user: User,
) -> None:
    now = timezone.now()
    matching = create_download(
        user,
        "matching.zip",
        created_at=now - timedelta(days=1),
    )
    create_download(user, "too-old.zip", created_at=now - timedelta(days=10))
    create_download(
        user,
        "failed.zip",
        creation_status=ZipFileStatus.Failed,
        created_at=now - timedelta(days=1),
    )

    response = authenticated_client.get(
        reverse("users:downloads-list"),
        {
            "status": "Ready",
            "created_at_start": (now - timedelta(days=2)).date().isoformat(),
            "created_at_end": now.date().isoformat(),
        },
    )

    rows = list(response.context["page_obj"])
    assert [row["filename"] for row in rows] == [matching.filename]


def test_default_order_uses_status_rank_then_newest_created(
    authenticated_client: Client,
    user: User,
) -> None:
    now = timezone.now()
    create_download(
        user,
        "older-ready.zip",
        created_at=now - timedelta(hours=2),
    )
    create_download(user, "newer-ready.zip", created_at=now - timedelta(hours=1))
    create_download(
        user,
        "pending.zip",
        creation_status=ZipFileStatus.Pending,
        created_at=now - timedelta(days=1),
    )

    response = authenticated_client.get(reverse("users:downloads-list"))

    assert [row["filename"] for row in response.context["page_obj"]] == [
        "pending.zip",
        "newer-ready.zip",
        "older-ready.zip",
    ]


def test_created_sort_supports_ascending_and_preserves_filter_query(
    authenticated_client: Client,
    user: User,
) -> None:
    now = timezone.now()
    create_download(user, "newer.zip", created_at=now)
    create_download(user, "older.zip", created_at=now - timedelta(days=1))

    response = authenticated_client.get(
        reverse("users:downloads-list"),
        {
            "status": "Ready",
            "sort_by": "created_at",
            "sort_order": "asc",
            "page": "1",
        },
    )

    assert [row["filename"] for row in response.context["page_obj"]] == [
        "older.zip",
        "newer.zip",
    ]
    querystring = response.context["search_querystring"]
    assert "status=Ready" in querystring
    assert "sort_by=created_at" in querystring
    assert "sort_order=asc" in querystring
    assert "page=" not in querystring


def test_list_paginates_at_25_rows(
    authenticated_client: Client,
    user: User,
) -> None:
    total_downloads = DownloadsListView.page_size + 1
    for index in range(total_downloads):
        create_download(user, f"download-{index}.zip")

    first_page = authenticated_client.get(reverse("users:downloads-list"))
    second_page = authenticated_client.get(
        reverse("users:downloads-list"),
        {"page": 2},
    )

    assert len(first_page.context["page_obj"]) == DownloadsListView.page_size
    assert len(second_page.context["page_obj"]) == 1
    assert first_page.context["page_obj"].paginator.count == total_downloads


def test_template_shows_downloaded_time_and_expected_links(
    authenticated_client: Client,
    user: User,
) -> None:
    create_download(user, "ready.zip")
    downloaded = create_download(user, "downloaded.zip", is_downloaded=True)
    create_download(
        user,
        "failed.zip",
        creation_status=ZipFileStatus.Failed,
    )

    response = authenticated_client.get(reverse("users:downloads-list"))
    content = response.content.decode()

    assert downloaded.downloaded_at.strftime("%Y") in content
    assert content.count(">Download</a>") == DOWNLOADABLE_STATUS_COUNT
    assert "ready.zip" in content
    assert "downloaded.zip" in content
