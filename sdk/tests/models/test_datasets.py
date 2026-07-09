"""Tests for the Dataset models."""

import uuid
from datetime import datetime
from datetime import timedelta

from pytz import UTC
from spectrumx.models.capture_enums import CaptureOrigin
from spectrumx.models.capture_enums import CaptureType
from spectrumx.models.datasets import Dataset
from spectrumx.models.datasets import DatasetCapture
from spectrumx.models.datasets import DatasetFile
from spectrumx.models.user import User


class TestDatasetFile:
    """Tests for the DatasetFile model."""

    def test_create_with_all_fields(self) -> None:
        """DatasetFile can be created with all fields."""
        uid = uuid.uuid4()
        ds_file = DatasetFile(
            uuid=uid,
            name="test_file.txt",
            directory="/test/dir",
            media_type="text/plain",
        )
        assert ds_file.uuid == uid
        assert ds_file.name == "test_file.txt"

    def test_create_with_defaults(self) -> None:
        """DatasetFile created with no args has all fields as None."""
        ds_file = DatasetFile()
        assert ds_file.uuid is None
        assert ds_file.name is None

    def test_extra_fields_ignored(self) -> None:
        """DatasetFile ignores extra fields via model_config extra='ignore'."""
        ds_file = DatasetFile.model_validate(
            {
                "uuid": str(uuid.uuid4()),
                "name": "test.txt",
                "unknown_field": "should be ignored",
            }
        )
        assert ds_file.name == "test.txt"
        assert not hasattr(ds_file, "unknown_field")


class TestDatasetCapture:
    """Tests for the DatasetCapture model."""

    def test_create_with_all_fields(self) -> None:
        """DatasetCapture can be created with all fields."""
        uid = uuid.uuid4()
        owner = User(name="Owner", email="owner@example.com")
        capture = DatasetCapture(
            uuid=uid,
            name="test_capture",
            capture_type=CaptureType.DigitalRF,
            index_name="captures-drf",
            origin=CaptureOrigin.User,
            top_level_dir="/c/tdir",
            owner=owner,
        )
        assert capture.uuid == uid
        assert capture.capture_type is CaptureType.DigitalRF
        assert capture.owner is not None
        assert capture.owner.name == "Owner"

    def test_create_with_defaults(self) -> None:
        """DatasetCapture created with no args has all fields as None."""
        capture = DatasetCapture()
        assert capture.uuid is None
        assert capture.name is None
        assert capture.capture_type is None
        assert capture.owner is None


class TestDataset:
    """Tests for the Dataset model."""

    def test_create_with_all_fields(self) -> None:
        """Dataset constructs with all fields — pin only load-bearing invariants."""
        uid = uuid.uuid4()
        owner = User(name="Owner", email="owner@example.com")
        now = datetime.now(tz=UTC)
        later = now + timedelta(days=1)

        ds_file = DatasetFile(name="file.txt", media_type="text/plain")
        ds_capture = DatasetCapture(
            name="cap", capture_type=CaptureType.SigMF, origin=CaptureOrigin.System
        )

        dataset = Dataset(
            uuid=uid,
            owner=owner,
            name="Test Dataset",
            abstract="An abstract",
            description="A description",
            doi="10.1234/test",
            authors=["Alice", "Bob"],
            license="MIT",
            keywords=["test", "spectrum"],
            institutions=["ND"],
            release_date=now,
            repository="https://example.com/repo",
            version=1,
            website="https://example.com",
            provenance={"source": "lab"},
            citation={"bibtex": "@article{...}"},
            other={"notes": "some notes"},
            created_at=now,
            updated_at=later,
            is_public=True,
            captures=[ds_capture],
            files=[ds_file],
        )
        # Load-bearing invariants only — full field-equality is getter ceremony.
        assert dataset.uuid == uid
        assert dataset.owner is not None
        assert dataset.owner.name == "Owner"
        assert dataset.is_deleted is False  # default preserved
        assert dataset.is_public is True  # explicit value honored
        assert dataset.release_date == now  # datetime parsing
        assert dataset.captures is not None
        assert len(dataset.captures) == 1
        assert dataset.files is not None
        assert len(dataset.files) == 1

    def test_create_with_defaults(self) -> None:
        """Dataset created with no args has default values."""
        dataset = Dataset()
        assert dataset.uuid is None
        assert dataset.owner is None
        assert dataset.name is None
        assert dataset.is_deleted is False
        assert dataset.is_public is False
        assert dataset.captures is None
        assert dataset.files is None

    def test_extra_fields_ignored(self) -> None:
        """Dataset ignores extra fields via model_config extra='ignore'."""
        dataset = Dataset.model_validate(
            {
                "name": "Test",
                "unknown_extra": "should be ignored",
            }
        )
        assert dataset.name == "Test"
        assert not hasattr(dataset, "unknown_extra")

    def test_parses_raw_gateway_payload_with_nested_coercion(self) -> None:
        """A gateway-shaped dict validates with nested coercing."""
        ds_uid = uuid.uuid4()
        cap_uid = uuid.uuid4()
        nested_capture = {
            "uuid": str(cap_uid),
            "name": "cap",
            "capture_type": CaptureType.DigitalRF.value,
            "index_name": "captures-drf",
            "origin": CaptureOrigin.User.value,
            "top_level_dir": "/c/tdir",
            "owner": {"name": "Cap Owner", "email": "cap@example.com"},
        }
        nested_file = {
            "uuid": str(uuid.uuid4()),
            "name": "f.txt",
            "media_type": "text/plain",
        }
        raw = {
            "uuid": str(ds_uid),
            "name": "Ds",
            "owner": {"name": "Owner", "email": "owner@example.com"},
            "description": "d",
            "captures": [nested_capture],
            "files": [nested_file],
        }
        dataset = Dataset.model_validate(raw)
        assert dataset.uuid == ds_uid
        assert isinstance(dataset.owner, User)
        assert dataset.owner.name == "Owner"
        assert dataset.captures is not None
        assert isinstance(dataset.captures[0], DatasetCapture)
        assert dataset.captures[0].capture_type is CaptureType.DigitalRF
        assert isinstance(dataset.captures[0].owner, User)
        assert dataset.files is not None
        assert isinstance(dataset.files[0], DatasetFile)

    def test_model_dump_round_trips(self) -> None:
        """model_validate(model_dump()) reconstructs an equal dataset."""
        dataset = Dataset(
            name="Round",
            owner=User(name="O", email="o@example.com"),
            captures=[
                DatasetCapture(name="c", capture_type=CaptureType.SigMF),
            ],
            files=[DatasetFile(name="f.txt")],
            keywords=["a", "b"],
        )
        rebuilt = Dataset.model_validate(dataset.model_dump())
        assert rebuilt.model_dump() == dataset.model_dump()
