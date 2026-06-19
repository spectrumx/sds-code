"""Contract tests: gateway federation export JSON ↔ sync Pydantic models."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from sds_gateway.api_methods.federation.export_contract import assert_field_names_match
from sds_gateway.api_methods.helpers.compile_federated_data import (
    compile_federated_capture_doc,
    compile_federated_dataset_doc,
)
from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.serializers.capture_serializers import (
    CaptureFederationSerializer,
)
from sds_gateway.api_methods.serializers.dataset_serializers import (
    DatasetFederationSerializer,
)
from sds_gateway.api_methods.tests.factories import CaptureFactory
from sds_gateway.api_methods.tests.factories import DatasetFactory

_repo_root = Path(__file__).resolve().parents[4]
_federation_root = _repo_root / "federation"
if _federation_root.is_dir():
    sys.path.insert(0, str(_federation_root))

pytest.importorskip("sds_federation")

from sds_federation.schemas.webhooks import (  # noqa: E402
    FederatedCaptureDoc,
    FederatedDatasetDoc,
)

User = get_user_model()


@pytest.mark.django_db
def test_dataset_export_field_names_match_pydantic() -> None:
    owner = User.objects.create(email="owner@example.com", is_approved=True)
    dataset = DatasetFactory(
        owner=owner,
        is_public=True,
        status=DatasetStatus.FINAL,
        keywords=None,
    )
    serializer = DatasetFederationSerializer(
        dataset,
        context={"site_name": "crc"},
    )
    assert_field_names_match(
        serializer,
        FederatedDatasetDoc,
        label="DatasetFederationSerializer",
    )


@pytest.mark.django_db
def test_capture_export_field_names_match_pydantic() -> None:
    owner = User.objects.create(email="cap-owner@example.com", is_approved=True)
    capture = CaptureFactory(owner=owner, is_public=True)
    serializer = CaptureFederationSerializer(
        capture,
        context={"site_name": "crc"},
    )
    assert_field_names_match(
        serializer,
        FederatedCaptureDoc,
        label="CaptureFederationSerializer",
    )


@pytest.mark.django_db
def test_compile_federated_dataset_doc_validates_against_pydantic() -> None:
    owner = User.objects.create(email="d@example.com", is_approved=True)
    dataset = DatasetFactory(
        owner=owner,
        is_public=True,
        status=DatasetStatus.FINAL,
        keywords=None,
    )
    payload = compile_federated_dataset_doc(dataset)
    FederatedDatasetDoc.model_validate(payload)


@pytest.mark.django_db
def test_compile_federated_capture_doc_validates_against_pydantic() -> None:
    owner = User.objects.create(email="c@example.com", is_approved=True)
    capture = CaptureFactory(owner=owner, is_public=True)
    payload = compile_federated_capture_doc(capture)
    FederatedCaptureDoc.model_validate(payload)
