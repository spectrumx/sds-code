"""Tests for QuickAddCaptureToDatasetView and UserDatasetsForQuickAddView."""

import json
import uuid
from typing import cast

import pytest
from django.test import Client
from django.urls import reverse
from rest_framework import status

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import PermissionLevel
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.tests.factories import DatasetFactory
from sds_gateway.users.models import User
from sds_gateway.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

QUICK_ADD_URL = "users:quick_add_capture_to_dataset"
DATASETS_URL = "users:datasets_for_quick_add"


def _post_quick_add(client: Client, dataset_uuid, capture_uuid):
    """Helper: POST to quick-add endpoint with JSON body."""
    return client.post(
        reverse(QUICK_ADD_URL),
        data=json.dumps(
            {"dataset_uuid": str(dataset_uuid), "capture_uuid": str(capture_uuid)}
        ),
        content_type="application/json",
    )


def _make_capture(owner: User, top_level_dir: str = "", **kwargs) -> Capture:
    """Create and save a minimal Capture owned by *owner*."""
    return Capture.objects.create(
        owner=owner,
        top_level_dir=top_level_dir or f"/captures/{uuid.uuid4()}",
        capture_type=CaptureType.DigitalRF,
        is_deleted=False,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# TestQuickAddCaptureToDatasetView
# ---------------------------------------------------------------------------


class TestQuickAddCaptureToDatasetView:
    """End-to-end tests for the quick-add POST endpoint."""

    @pytest.fixture
    def client(self) -> Client:
        return Client()

    @pytest.fixture
    def owner(self) -> User:
        return cast("User", UserFactory(is_approved=True))

    @pytest.fixture
    def other_user(self) -> User:
        return cast("User", UserFactory(is_approved=True))

    @pytest.fixture
    def dataset(self, owner: User):
        return DatasetFactory(owner=owner, is_public=False, keywords=None)

    @pytest.fixture
    def capture(self, owner: User) -> Capture:
        return _make_capture(owner)

    # ---------- Auth ----------

    def test_unauthenticated_returns_redirect(self, client: Client, capture, dataset):
        """Unauthenticated requests redirect to the Auth0 login page."""
        response = _post_quick_add(client, dataset.uuid, capture.uuid)
        assert response.status_code == status.HTTP_302_FOUND
        assert reverse("auth0_login") in response["Location"]

    # ---------- Request validation ----------

    @pytest.mark.parametrize(
        ("build_payload", "expected_field"),
        [
            pytest.param(
                lambda d, c: {"capture_uuid": str(c)},
                "dataset_uuid",
                id="missing-dataset-uuid",
            ),
            pytest.param(
                lambda d, c: {"dataset_uuid": str(d)},
                "capture_uuid",
                id="missing-capture-uuid",
            ),
            pytest.param(
                lambda d, c: {"dataset_uuid": "not-a-uuid", "capture_uuid": str(c)},
                "dataset_uuid",
                id="invalid-dataset-uuid",
            ),
            pytest.param(
                lambda d, c: {"dataset_uuid": str(d), "capture_uuid": "bad-uuid"},
                "capture_uuid",
                id="invalid-capture-uuid",
            ),
        ],
    )
    def test_uuid_validation_returns_400(
        self,
        client: Client,
        owner: User,
        capture: Capture,
        dataset,
        build_payload,
        expected_field: str,
    ):
        client.force_login(owner)
        response = client.post(
            reverse(QUICK_ADD_URL),
            data=json.dumps(build_payload(dataset.uuid, capture.uuid)),
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert expected_field in response.json()["error"]

    def test_wrong_content_type_returns_400(self, client: Client, owner: User):
        client.force_login(owner)
        response = client.post(
            reverse(QUICK_ADD_URL),
            data={"dataset_uuid": "x", "capture_uuid": "y"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Content-Type" in response.json()["error"]

    def test_invalid_json_body_returns_400(self, client: Client, owner: User):
        client.force_login(owner)
        response = client.post(
            reverse(QUICK_ADD_URL),
            data="this is not json",
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json()["error"] == "Invalid JSON body"

    # ---------- Object-not-found cases ----------

    def test_nonexistent_capture_returns_404(
        self, client: Client, owner: User, dataset
    ):
        client.force_login(owner)
        response = _post_quick_add(client, dataset.uuid, uuid.uuid4())
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Capture" in response.json()["error"]

    def test_capture_owned_by_other_user_returns_404(
        self, client: Client, owner: User, other_user: User, dataset
    ):
        """The capture exists but belongs to another user — must look like 404."""
        other_capture = _make_capture(other_user)
        client.force_login(owner)
        response = _post_quick_add(client, dataset.uuid, other_capture.uuid)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_nonexistent_dataset_returns_404(
        self, client: Client, owner: User, capture: Capture
    ):
        client.force_login(owner)
        response = _post_quick_add(client, uuid.uuid4(), capture.uuid)
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "Dataset" in response.json()["error"]

    def test_public_dataset_returns_403(
        self, client: Client, owner: User, capture: Capture
    ):
        """Public datasets are published and cannot be modified via quick-add."""
        public_dataset = DatasetFactory(owner=owner, is_public=True, keywords=None)
        client.force_login(owner)
        response = _post_quick_add(client, public_dataset.uuid, capture.uuid)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "published" in response.json()["error"].lower()

    def test_deleted_dataset_returns_404(
        self, client: Client, owner: User, capture: Capture
    ):
        deleted = DatasetFactory(
            owner=owner, is_public=False, is_deleted=True, keywords=None
        )
        client.force_login(owner)
        response = _post_quick_add(client, deleted.uuid, capture.uuid)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    # ---------- Permission checks ----------

    def test_viewer_cannot_add_captures(self, client: Client, other_user: User):
        """A user with VIEWER permission cannot add captures to the dataset."""
        dataset_owner = cast("User", UserFactory(is_approved=True))
        dataset = DatasetFactory(owner=dataset_owner, keywords=None)
        UserSharePermission.objects.create(
            owner=dataset_owner,
            shared_with=other_user,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            permission_level=PermissionLevel.VIEWER,
        )
        other_capture = _make_capture(other_user)
        client.force_login(other_user)
        response = _post_quick_add(client, dataset.uuid, other_capture.uuid)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "permission" in response.json()["error"].lower()

    def test_contributor_can_add_captures(self, client: Client, other_user: User):
        """A CONTRIBUTOR can add their own capture to a shared dataset."""
        dataset_owner = cast("User", UserFactory(is_approved=True))
        dataset = DatasetFactory(owner=dataset_owner, keywords=None)
        UserSharePermission.objects.create(
            owner=dataset_owner,
            shared_with=other_user,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            permission_level=PermissionLevel.CONTRIBUTOR,
        )
        capture = _make_capture(other_user)
        client.force_login(other_user)
        response = _post_quick_add(client, dataset.uuid, capture.uuid)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True

    def test_co_owner_can_add_captures(self, client: Client, other_user: User):
        """A CO_OWNER can add their own capture to a shared dataset."""
        dataset_owner = cast("User", UserFactory(is_approved=True))
        dataset = DatasetFactory(owner=dataset_owner, keywords=None)
        UserSharePermission.objects.create(
            owner=dataset_owner,
            shared_with=other_user,
            item_type=ItemType.DATASET,
            item_uuid=dataset.uuid,
            permission_level=PermissionLevel.CO_OWNER,
        )
        capture = _make_capture(other_user)
        client.force_login(other_user)
        response = _post_quick_add(client, dataset.uuid, capture.uuid)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True

    # ---------- Success cases ----------

    def test_owner_adds_single_capture_successfully(
        self, client: Client, owner: User, dataset, capture: Capture
    ):
        client.force_login(owner)
        response = _post_quick_add(client, dataset.uuid, capture.uuid)

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert payload["success"] is True
        assert str(capture.uuid) in payload["added"]
        assert payload["skipped"] == []
        assert payload["errors"] == []

        dataset.refresh_from_db()
        assert dataset.captures.filter(uuid=capture.uuid).exists()

    def test_adding_already_present_capture_is_skipped(
        self, client: Client, owner: User, dataset, capture: Capture
    ):
        dataset.captures.add(capture)
        client.force_login(owner)
        response = _post_quick_add(client, dataset.uuid, capture.uuid)

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert payload["success"] is True
        assert payload["added"] == []
        assert str(capture.uuid) in payload["skipped"]

    def test_second_add_of_same_capture_is_idempotent(
        self, client: Client, owner: User, dataset, capture: Capture
    ):
        """Calling quick-add twice returns skipped on the second call."""
        client.force_login(owner)
        _post_quick_add(client, dataset.uuid, capture.uuid)
        response = _post_quick_add(client, dataset.uuid, capture.uuid)

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert str(capture.uuid) in payload["skipped"]

    # ---------- Multi-channel grouping ----------

    def test_multi_channel_capture_adds_all_channels(
        self, client: Client, owner: User, dataset
    ):
        """Sending any single channel of a multi-channel capture adds all siblings."""
        shared_dir = f"/captures/{uuid.uuid4()}"
        ch1 = _make_capture(owner, top_level_dir=shared_dir, channel="ch0")
        ch2 = _make_capture(owner, top_level_dir=shared_dir, channel="ch1")

        client.force_login(owner)
        response = _post_quick_add(client, dataset.uuid, ch1.uuid)

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert payload["success"] is True
        added_uuids = set(payload["added"])
        assert str(ch1.uuid) in added_uuids
        assert str(ch2.uuid) in added_uuids
        assert dataset.captures.filter(uuid=ch2.uuid).exists()

    def test_multi_channel_partial_already_in_dataset(
        self, client: Client, owner: User, dataset
    ):
        """If one channel is already in the dataset, it's skipped; sibling is added."""
        shared_dir = f"/captures/{uuid.uuid4()}"
        ch1 = _make_capture(owner, top_level_dir=shared_dir, channel="ch0")
        ch2 = _make_capture(owner, top_level_dir=shared_dir, channel="ch1")
        dataset.captures.add(ch1)

        client.force_login(owner)
        response = _post_quick_add(client, dataset.uuid, ch1.uuid)

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert str(ch1.uuid) in payload["skipped"]
        assert str(ch2.uuid) in payload["added"]


# ---------------------------------------------------------------------------
# TestUserDatasetsForQuickAddView
# ---------------------------------------------------------------------------


class TestUserDatasetsForQuickAddView:
    """Tests for the GET endpoint that populates the dataset dropdown."""

    @pytest.fixture
    def client(self) -> Client:
        return Client()

    @pytest.fixture
    def owner(self) -> User:
        return cast("User", UserFactory(is_approved=True))

    @pytest.fixture
    def other_user(self) -> User:
        return cast("User", UserFactory(is_approved=True))

    def _get(self, client: Client):
        return client.get(reverse(DATASETS_URL))

    # ---------- Auth ----------

    def test_unauthenticated_redirected(self, client: Client):
        """Unauthenticated requests redirect to the Auth0 login page."""
        response = self._get(client)
        assert response.status_code == status.HTTP_302_FOUND
        assert reverse("auth0_login") in response["Location"]

    # ---------- Owned datasets ----------

    def test_returns_owned_private_datasets(self, client: Client, owner: User):
        ds = DatasetFactory(owner=owner, is_public=False, keywords=None)
        client.force_login(owner)
        response = self._get(client)

        assert response.status_code == status.HTTP_200_OK
        uuids = [d["uuid"] for d in response.json()["datasets"]]
        assert str(ds.uuid) in uuids

    def test_excludes_owned_public_datasets(self, client: Client, owner: User):
        """Public datasets should not appear (they can't be modified)."""
        public_ds = DatasetFactory(owner=owner, is_public=True, keywords=None)
        client.force_login(owner)
        response = self._get(client)

        uuids = [d["uuid"] for d in response.json()["datasets"]]
        assert str(public_ds.uuid) not in uuids

    def test_excludes_deleted_datasets(self, client: Client, owner: User):
        deleted = DatasetFactory(
            owner=owner, is_deleted=True, is_public=False, keywords=None
        )
        client.force_login(owner)
        response = self._get(client)

        uuids = [d["uuid"] for d in response.json()["datasets"]]
        assert str(deleted.uuid) not in uuids

    # ---------- Shared datasets ----------

    def test_includes_shared_dataset_with_contributor_permission(
        self, client: Client, owner: User, other_user: User
    ):
        ds = DatasetFactory(owner=other_user, is_public=False, keywords=None)
        UserSharePermission.objects.create(
            owner=other_user,
            shared_with=owner,
            item_type=ItemType.DATASET,
            item_uuid=ds.uuid,
            permission_level=PermissionLevel.CONTRIBUTOR,
        )
        client.force_login(owner)
        response = self._get(client)

        uuids = [d["uuid"] for d in response.json()["datasets"]]
        assert str(ds.uuid) in uuids

    def test_includes_shared_dataset_with_co_owner_permission(
        self, client: Client, owner: User, other_user: User
    ):
        ds = DatasetFactory(owner=other_user, is_public=False, keywords=None)
        UserSharePermission.objects.create(
            owner=other_user,
            shared_with=owner,
            item_type=ItemType.DATASET,
            item_uuid=ds.uuid,
            permission_level=PermissionLevel.CO_OWNER,
        )
        client.force_login(owner)
        response = self._get(client)

        uuids = [d["uuid"] for d in response.json()["datasets"]]
        assert str(ds.uuid) in uuids

    def test_excludes_shared_dataset_with_viewer_permission(
        self, client: Client, owner: User, other_user: User
    ):
        """VIEWERs cannot add captures, so the dataset must not appear."""
        ds = DatasetFactory(owner=other_user, is_public=False, keywords=None)
        UserSharePermission.objects.create(
            owner=other_user,
            shared_with=owner,
            item_type=ItemType.DATASET,
            item_uuid=ds.uuid,
            permission_level=PermissionLevel.VIEWER,
        )
        client.force_login(owner)
        response = self._get(client)

        uuids = [d["uuid"] for d in response.json()["datasets"]]
        assert str(ds.uuid) not in uuids

    def test_excludes_shared_dataset_with_disabled_permission(
        self, client: Client, owner: User, other_user: User
    ):
        ds = DatasetFactory(owner=other_user, is_public=False, keywords=None)
        UserSharePermission.objects.create(
            owner=other_user,
            shared_with=owner,
            item_type=ItemType.DATASET,
            item_uuid=ds.uuid,
            permission_level=PermissionLevel.CONTRIBUTOR,
            is_enabled=False,
        )
        client.force_login(owner)
        response = self._get(client)

        uuids = [d["uuid"] for d in response.json()["datasets"]]
        assert str(ds.uuid) not in uuids

    def test_owned_dataset_appears_exactly_once(self, client: Client, owner: User):
        """Owned dataset must not appear twice even if it matches the shared filter."""
        ds = DatasetFactory(owner=owner, is_public=False, keywords=None)
        client.force_login(owner)
        response = self._get(client)

        uuids = [d["uuid"] for d in response.json()["datasets"]]
        assert uuids.count(str(ds.uuid)) == 1

    def test_self_shared_dataset_appears_exactly_once(
        self, client: Client, owner: User
    ):
        """Owned dataset with a self-share permission must not appear twice.

        The view's .exclude(owner=user) guard prevents it appearing in both
        the owned and the shared sections of the response.
        """
        ds = DatasetFactory(owner=owner, is_public=False, keywords=None)
        UserSharePermission.objects.create(
            owner=owner,
            shared_with=owner,
            item_type=ItemType.DATASET,
            item_uuid=ds.uuid,
            permission_level=PermissionLevel.CONTRIBUTOR,
        )
        client.force_login(owner)
        response = self._get(client)

        uuids = [d["uuid"] for d in response.json()["datasets"]]
        assert uuids.count(str(ds.uuid)) == 1

    # ---------- Response shape ----------

    def test_response_contains_uuid_and_name(self, client: Client, owner: User):
        ds = DatasetFactory(
            owner=owner, is_public=False, name="My Dataset", keywords=None
        )
        client.force_login(owner)
        response = self._get(client)

        datasets = response.json()["datasets"]
        entry = next((d for d in datasets if d["uuid"] == str(ds.uuid)), None)
        assert entry is not None, "Created dataset not present in response"
        assert entry["uuid"] == str(ds.uuid)
        assert entry["name"] == "My Dataset"

    def test_unnamed_dataset_shows_fallback(self, client: Client, owner: User):
        ds = DatasetFactory(owner=owner, is_public=False, name="", keywords=None)
        client.force_login(owner)
        response = self._get(client)

        entry = next(
            (d for d in response.json()["datasets"] if d["uuid"] == str(ds.uuid)),
            None,
        )
        assert entry is not None
        assert entry["name"] == "Unnamed"
