"""Tests for federation export endpoints and API key scoping."""

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.models import KeySources
from sds_gateway.api_methods.tests.factories import CaptureFactory
from sds_gateway.api_methods.tests.factories import DatasetFactory
from sds_gateway.users.models import UserAPIKey

User = get_user_model()


class FederationExportAPITest(APITestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create(email="owner@example.com", is_approved=True)
        self.sync_user = User.objects.create(
            email="sync@internal.local",
            is_approved=True,
        )
        _obj, self.sync_key = UserAPIKey.objects.create_key(
            name="sync",
            user=self.sync_user,
            source=KeySources.FederationSync,
        )
        _obj, self.user_key = UserAPIKey.objects.create_key(
            name="regular",
            user=self.owner,
            source=KeySources.SDSWebUI,
        )
        self.public_dataset = DatasetFactory(
            owner=self.owner,
            is_public=True,
            status=DatasetStatus.FINAL,
            keywords=None,
        )
        self.private_dataset = DatasetFactory(
            owner=self.owner,
            is_public=False,
            status=DatasetStatus.DRAFT,
            keywords=None,
        )
        self.public_capture = CaptureFactory(owner=self.owner, is_public=True)
        self.list_datasets_url = reverse(
            "api:federation-export-datasets-list",
        )
        self.detail_dataset_url = reverse(
            "api:federation-export-dataset-detail",
            kwargs={"pk": str(self.public_dataset.uuid)},
        )
        self.list_captures_url = reverse(
            "api:federation-export-captures-list",
        )

    def _auth(self, key: str) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Api-Key: {key}"}

    def test_sync_key_can_list_public_datasets(self) -> None:
        response = self.client.get(self.list_datasets_url, **self._auth(self.sync_key))
        assert response.status_code == status.HTTP_200_OK
        uuids = {row["uuid"] for row in response.json()}
        assert str(self.public_dataset.uuid) in uuids
        assert str(self.private_dataset.uuid) not in uuids

    def test_sync_key_can_retrieve_public_dataset(self) -> None:
        response = self.client.get(
            self.detail_dataset_url,
            **self._auth(self.sync_key),
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["uuid"] == str(self.public_dataset.uuid)
        assert response.json()["site_name"]

    def test_regular_key_denied_on_export(self) -> None:
        response = self.client.get(self.list_datasets_url, **self._auth(self.user_key))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_sync_key_denied_on_dataset_assets_api(self) -> None:
        url = reverse(
            "api:datasets-detail",
            kwargs={"pk": str(self.public_dataset.uuid)},
        )
        response = self.client.get(url, **self._auth(self.sync_key))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_sync_key_denied_on_capture_list(self) -> None:
        url = reverse("api:captures-list")
        response = self.client.get(url, **self._auth(self.sync_key))
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_export_captures_list(self) -> None:
        response = self.client.get(self.list_captures_url, **self._auth(self.sync_key))
        assert response.status_code == status.HTTP_200_OK
        uuids = {row["uuid"] for row in response.json()}
        assert str(self.public_capture.uuid) in uuids
