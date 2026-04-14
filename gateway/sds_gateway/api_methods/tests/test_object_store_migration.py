"""Tests for object-store migration adapter and dual Django storage backend."""

# ruff: noqa: SLF001
# pyright: reportPrivateUsage=false

import logging
from unittest.mock import MagicMock

import pytest
from django.core.files.base import ContentFile

from sds_gateway.api_methods.utils.dual_object_store_storage import (
    DualObjectStoreS3Storage,
)
from sds_gateway.api_methods.utils.minio_client import ObjectStoreFacade


class MissingObjectError(Exception):
    """Test-only exception to simulate missing-object failures."""

    code = "NoSuchKey"


def _configure_bucket_settings(settings) -> None:
    settings.SFS_STORAGE_BUCKET_NAME = "sfs-bucket"
    settings.MINIO_STORAGE_BUCKET_NAME = "minio-bucket"


def _build_storage_with_mocks(
    *,
    monkeypatch: pytest.MonkeyPatch,
    settings,
    primary_storage: MagicMock,
    secondary_storage: MagicMock,
    read_fallback_enabled: bool,
    write_both_enabled: bool,
    dual_write_strict: bool,
) -> DualObjectStoreS3Storage:
    settings.OBJECT_STORE_READ_FALLBACK_TO_MINIO_ENABLED = read_fallback_enabled
    settings.OBJECT_STORE_WRITE_BOTH_ENABLED = write_both_enabled
    settings.OBJECT_STORE_DUAL_WRITE_STRICT = dual_write_strict

    backends = [primary_storage, secondary_storage]

    def _create_backend(_self, *, store_prefix: str):
        _ = store_prefix
        return backends.pop(0)

    monkeypatch.setattr(DualObjectStoreS3Storage, "_create_backend", _create_backend)
    return DualObjectStoreS3Storage()


def test_adapter_read_falls_back_on_missing(settings) -> None:
    _configure_bucket_settings(settings)

    primary_client = MagicMock()
    secondary_client = MagicMock()

    expected_response = object()
    primary_client.get_object.side_effect = MissingObjectError("missing")
    secondary_client.get_object.return_value = expected_response

    facade = ObjectStoreFacade(
        primary_client=primary_client,
        secondary_client=secondary_client,
        read_fallback_to_secondary_enabled=True,
        write_both_enabled=False,
        dual_write_strict=False,
    )

    result = facade.get_object(bucket_name="bucket", object_name="path/to/object")

    assert result is expected_response
    secondary_client.get_object.assert_called_once_with(
        bucket_name="minio-bucket",
        object_name="path/to/object",
    )


def test_adapter_does_not_fallback_on_non_missing_errors(settings) -> None:
    """Only missing-object errors should trigger fallback when enabled, other errors
    should raise immediately."""
    _configure_bucket_settings(settings)

    primary_client = MagicMock()
    secondary_client = MagicMock()

    primary_client.get_object.side_effect = RuntimeError("boom")

    facade = ObjectStoreFacade(
        primary_client=primary_client,
        secondary_client=secondary_client,
        read_fallback_to_secondary_enabled=True,
        write_both_enabled=False,
        dual_write_strict=False,
    )

    with pytest.raises(RuntimeError, match="boom"):
        facade.get_object(bucket_name="bucket", object_name="path/to/object")

    secondary_client.get_object.assert_not_called()


def test_adapter_dual_write_non_strict_allows_secondary_failure(settings) -> None:
    """In non-strict dual-write mode, secondary write failures should not raise and
    should be logged."""
    _configure_bucket_settings(settings)

    primary_client = MagicMock()
    secondary_client = MagicMock()

    primary_client.put_object.return_value = "primary-result"
    secondary_client.put_object.side_effect = RuntimeError("secondary write failed")

    facade = ObjectStoreFacade(
        primary_client=primary_client,
        secondary_client=secondary_client,
        read_fallback_to_secondary_enabled=False,
        write_both_enabled=True,
        dual_write_strict=False,
    )

    result = facade.put_object(bucket_name="bucket", object_name="path/to/object")

    assert result == "primary-result"


def test_adapter_dual_write_strict_raises_on_secondary_failure(settings) -> None:
    _configure_bucket_settings(settings)

    primary_client = MagicMock()
    secondary_client = MagicMock()

    primary_client.put_object.return_value = "primary-result"
    secondary_client.put_object.side_effect = RuntimeError("secondary write failed")

    facade = ObjectStoreFacade(
        primary_client=primary_client,
        secondary_client=secondary_client,
        read_fallback_to_secondary_enabled=False,
        write_both_enabled=True,
        dual_write_strict=True,
    )

    with pytest.raises(RuntimeError, match="secondary write failed"):
        facade.put_object(bucket_name="bucket", object_name="path/to/object")


def test_adapter_maps_bucket_name_kwargs_per_store(settings) -> None:
    _configure_bucket_settings(settings)

    primary_client = MagicMock()
    secondary_client = MagicMock()

    primary_client.put_object.return_value = "primary-result"

    facade = ObjectStoreFacade(
        primary_client=primary_client,
        secondary_client=secondary_client,
        read_fallback_to_secondary_enabled=False,
        write_both_enabled=True,
        dual_write_strict=False,
    )

    facade.put_object(bucket_name="caller-bucket", object_name="path/to/object")

    primary_client.put_object.assert_called_once_with(
        bucket_name="sfs-bucket",
        object_name="path/to/object",
    )
    secondary_client.put_object.assert_called_once_with(
        bucket_name="minio-bucket",
        object_name="path/to/object",
    )


def test_adapter_maps_bucket_name_positionally_per_store(settings) -> None:
    _configure_bucket_settings(settings)

    primary_client = MagicMock()
    secondary_client = MagicMock()

    facade = ObjectStoreFacade(
        primary_client=primary_client,
        secondary_client=secondary_client,
        read_fallback_to_secondary_enabled=False,
        write_both_enabled=True,
        dual_write_strict=False,
    )

    facade.remove_object("caller-bucket", "path/to/object")

    primary_client.remove_object.assert_called_once_with(
        "sfs-bucket",
        "path/to/object",
    )
    secondary_client.remove_object.assert_called_once_with(
        "minio-bucket",
        "path/to/object",
    )


def test_adapter_remove_object_is_strict_when_fallback_is_enabled(settings) -> None:
    _configure_bucket_settings(settings)

    primary_client = MagicMock()
    secondary_client = MagicMock()

    secondary_client.remove_object.side_effect = RuntimeError("secondary delete failed")

    facade = ObjectStoreFacade(
        primary_client=primary_client,
        secondary_client=secondary_client,
        read_fallback_to_secondary_enabled=True,
        write_both_enabled=False,
        dual_write_strict=False,
    )

    with pytest.raises(RuntimeError, match="secondary delete failed"):
        facade.remove_object(bucket_name="bucket", object_name="path/to/object")


def test_adapter_fallback_logging_redacts_object_key(
    caplog: pytest.LogCaptureFixture,
    settings,
) -> None:
    _configure_bucket_settings(settings)

    primary_client = MagicMock()
    secondary_client = MagicMock()

    full_key = "customers/acme-corp/private/export-2026-04-14.csv"
    primary_client.get_object.side_effect = MissingObjectError("missing")
    secondary_client.get_object.return_value = object()

    facade = ObjectStoreFacade(
        primary_client=primary_client,
        secondary_client=secondary_client,
        read_fallback_to_secondary_enabled=True,
        write_both_enabled=False,
        dual_write_strict=False,
    )

    with caplog.at_level(
        logging.WARNING,
        logger="sds_gateway.api_methods.utils.minio_client",
    ):
        facade.get_object(bucket_name="bucket", object_name=full_key)

    logged_messages = " ".join(record.getMessage() for record in caplog.records)
    assert full_key not in logged_messages
    assert "sha256=" in logged_messages
    assert "len=" in logged_messages


def test_storage_open_falls_back_on_missing(
    monkeypatch: pytest.MonkeyPatch,
    settings,
) -> None:
    primary_storage = MagicMock()
    secondary_storage = MagicMock()

    expected_file = MagicMock()
    primary_storage._open.side_effect = MissingObjectError("missing")
    secondary_storage._open.return_value = expected_file

    storage = _build_storage_with_mocks(
        monkeypatch=monkeypatch,
        settings=settings,
        primary_storage=primary_storage,
        secondary_storage=secondary_storage,
        read_fallback_enabled=True,
        write_both_enabled=False,
        dual_write_strict=False,
    )

    result = storage._open("path/to/object", mode="rb")

    assert result is expected_file
    secondary_storage._open.assert_called_once_with("path/to/object", mode="rb")


def test_storage_save_dual_write_non_strict(
    monkeypatch: pytest.MonkeyPatch,
    settings,
) -> None:
    primary_storage = MagicMock()
    secondary_storage = MagicMock()

    primary_storage._save.return_value = "saved/name.bin"
    secondary_storage._save.side_effect = RuntimeError("secondary save failed")

    storage = _build_storage_with_mocks(
        monkeypatch=monkeypatch,
        settings=settings,
        primary_storage=primary_storage,
        secondary_storage=secondary_storage,
        read_fallback_enabled=False,
        write_both_enabled=True,
        dual_write_strict=False,
    )

    content = ContentFile(b"payload", name="name.bin")
    saved_name = storage._save("name.bin", content)

    assert saved_name == "saved/name.bin"
    secondary_storage._save.assert_called_once()


def test_storage_delete_is_strict_when_fallback_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
    settings,
) -> None:
    primary_storage = MagicMock()
    secondary_storage = MagicMock()

    secondary_storage.delete.side_effect = RuntimeError("secondary delete failed")

    storage = _build_storage_with_mocks(
        monkeypatch=monkeypatch,
        settings=settings,
        primary_storage=primary_storage,
        secondary_storage=secondary_storage,
        read_fallback_enabled=True,
        write_both_enabled=False,
        dual_write_strict=False,
    )

    with pytest.raises(RuntimeError, match="secondary delete failed"):
        storage.delete("path/to/object")
