"""Tests for federation export endpoints and API key scoping."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.models import KeySources
from sds_gateway.api_methods.federation.compile_federated_data import (
    compile_federated_dataset_doc,
)
from sds_gateway.api_methods.tests.factories import CaptureFactory
from sds_gateway.api_methods.tests.factories import DatasetFactory
from sds_gateway.users.models import UserAPIKey

User = get_user_model()


@override_settings(
    FEDERATION_ENABLED=True,
    FEDERATION_SITE_NAME="crc",
    FEDERATION_OPERATIONAL_OVERRIDE=True,
    FEDERATION_EXPORT_ALLOWED_CIDRS=["0.0.0.0/0", "::/0"],
)
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
        response = self.client.get(
            self.list_datasets_url,
            REMOTE_ADDR="127.0.0.1",
            **self._auth(self.sync_key),
        )
        assert response.status_code == status.HTTP_200_OK
        uuids = {row["uuid"] for row in response.json()}
        assert str(self.public_dataset.uuid) in uuids
        assert str(self.private_dataset.uuid) not in uuids

    def test_sync_key_can_retrieve_public_dataset(self) -> None:
        indexed = compile_federated_dataset_doc(self.public_dataset)
        with patch(
            "sds_gateway.api_methods.views.federation_endpoints."
            "get_federated_export_doc_by_uuid",
            return_value=indexed,
        ):
            response = self.client.get(
                self.detail_dataset_url,
                REMOTE_ADDR="127.0.0.1",
                **self._auth(self.sync_key),
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["uuid"] == str(self.public_dataset.uuid)
        assert response.json()["site_name"] == "crc"

    def test_sync_key_dataset_detail_404_when_not_indexed(self) -> None:
        with patch(
            "sds_gateway.api_methods.views.federation_endpoints."
            "get_federated_export_doc_by_uuid",
            return_value=None,
        ):
            response = self.client.get(
                self.detail_dataset_url,
                REMOTE_ADDR="127.0.0.1",
                **self._auth(self.sync_key),
            )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_regular_key_denied_on_export(self) -> None:
        response = self.client.get(
            self.list_datasets_url,
            REMOTE_ADDR="127.0.0.1",
            **self._auth(self.user_key),
        )
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
        response = self.client.get(
            self.list_captures_url,
            REMOTE_ADDR="127.0.0.1",
            **self._auth(self.sync_key),
        )
        assert response.status_code == status.HTTP_200_OK
        uuids = {row["uuid"] for row in response.json()}
        assert str(self.public_capture.uuid) in uuids
