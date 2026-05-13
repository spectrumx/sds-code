"""Dual-store Django storage backend for primary + secondary.

Primary and secondary backends might be any S3-compatible object store, usually among:
- Primary:      RustFS (local/CI), SeaweedFS (production), or MinIO (deprecated)
- Secondary:    RustFS, Garage, or MinIO (deprecated)

Sec is optional, unless any of these are True:
    - OBJECT_STORE_READ_FALLBACK_TO_SECONDARY_ENABLED
    - OBJECT_STORE_WRITE_BOTH_ENABLED
    - OBJECT_STORE_DUAL_WRITE_STRICT
"""

import hashlib
import logging
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.base import File
from django.core.files.storage import Storage
from storages.backends.s3boto3 import S3Boto3Storage

log = logging.getLogger(__name__)

_MISSING_OBJECT_ERROR_CODES = {
    "404",
    "NoSuchBucket",
    "NoSuchKey",
    "NoSuchObject",
    "NoSuchVersion",
    "NotFound",
}


def _is_missing_object_error(error: Exception) -> bool:
    """Return True when error represents missing object/bucket condition."""
    error_code = str(getattr(error, "code", ""))
    if error_code in _MISSING_OBJECT_ERROR_CODES:
        return True

    response = getattr(error, "response", None)
    if isinstance(response, dict):
        response_error = response.get("Error", {})
        code = str(response_error.get("Code", ""))
        if code in _MISSING_OBJECT_ERROR_CODES:
            return True

    status_code = str(getattr(error, "status", ""))
    return status_code == "404"


def _build_storage_options(store_prefix: str) -> dict[str, Any]:
    """Build S3Boto3Storage options for a configured object store prefix."""
    return {
        "access_key": getattr(settings, f"{store_prefix}_ACCESS_KEY_ID"),
        "secret_key": getattr(settings, f"{store_prefix}_SECRET_ACCESS_KEY"),
        "bucket_name": getattr(settings, f"{store_prefix}_STORAGE_BUCKET_NAME"),
        "endpoint_url": getattr(settings, f"{store_prefix}_S3_ENDPOINT_URL"),
        "region_name": settings.AWS_S3_REGION_NAME,
        "signature_version": settings.AWS_S3_SIGNATURE_VERSION,
        "default_acl": settings.AWS_DEFAULT_ACL,
        "file_overwrite": settings.AWS_S3_FILE_OVERWRITE,
    }


def _is_secondary_configured() -> bool:
    """Return True when a secondary object store is explicitly configured."""
    return getattr(settings, "SECONDARY_ACCESS_KEY_ID", None) != getattr(
        settings, "LEGACY_AWS_ACCESS_KEY_ID", None
    )


def _safe_object_reference(name: str) -> str:
    """Return a non-reversible identifier suitable for operational logs."""
    object_name_digest = hashlib.sha256(name.encode()).hexdigest()[:12]
    return f"sha256={object_name_digest} len={len(name)}"


class DualObjectStoreS3Storage(Storage):
    """Django storage backend with primary and fallback."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._primary_storage = self._create_backend(store_prefix="PRIMARY")
        self._secondary_storage: S3Boto3Storage | None = (
            self._create_backend(store_prefix="SECONDARY")
            if _is_secondary_configured()
            else None
        )

    def _create_backend(self, *, store_prefix: str) -> S3Boto3Storage:
        """Create storage backend for a given settings prefix."""
        return S3Boto3Storage(**_build_storage_options(store_prefix=store_prefix))

    def _clone_content(self, content: File[Any]) -> ContentFile[Any]:
        """Clone content for secondary writes while preserving the primary stream."""
        if hasattr(content, "seek"):
            content.seek(0)
        payload = content.read()
        if isinstance(payload, str):
            payload = payload.encode()
        if hasattr(content, "seek"):
            content.seek(0)

        return ContentFile(payload, name=getattr(content, "name", None))

    def _open(self, name: str, mode: str = "rb") -> File[Any]:
        try:
            return self._primary_storage._open(name, mode=mode)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        except Exception as error:
            if not settings.OBJECT_STORE_READ_FALLBACK_TO_SECONDARY_ENABLED:
                raise
            if not _is_missing_object_error(error):
                raise
            if not self._secondary_storage:
                raise

            log.warning(
                "Object %s not in primary storage, falling back to secondary",
                _safe_object_reference(name),
            )
            return self._secondary_storage._open(name, mode=mode)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

    def _save(self, name: str, content: File[Any]) -> str:
        if not settings.OBJECT_STORE_WRITE_BOTH_ENABLED:
            return self._primary_storage._save(name, content)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

        if not self._secondary_storage:
            return self._primary_storage._save(name, content)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

        secondary_content = self._clone_content(content)
        saved_name = self._primary_storage._save(name, content)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001

        try:
            self._secondary_storage._save(saved_name, secondary_content)  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
        except Exception:
            if settings.OBJECT_STORE_DUAL_WRITE_STRICT:
                raise

            log.exception(
                "Secondary storage write failed in non-strict dual-write mode"
            )

        return saved_name

    def exists(self, name: str) -> bool:
        if self._primary_storage.exists(name):
            return True

        if settings.OBJECT_STORE_READ_FALLBACK_TO_SECONDARY_ENABLED:
            if self._secondary_storage:
                return self._secondary_storage.exists(name)

        return False

    def delete(self, name: str) -> None:
        self._primary_storage.delete(name)
        if not (
            settings.OBJECT_STORE_WRITE_BOTH_ENABLED
            or settings.OBJECT_STORE_READ_FALLBACK_TO_SECONDARY_ENABLED
        ):
            return

        if not self._secondary_storage:
            return

        try:
            self._secondary_storage.delete(name)
        except Exception:
            if (
                settings.OBJECT_STORE_READ_FALLBACK_TO_SECONDARY_ENABLED
                or settings.OBJECT_STORE_DUAL_WRITE_STRICT
            ):
                raise

            log.exception(
                "Secondary storage delete failed in non-strict dual-write mode"
            )

    def size(self, name: str) -> int:
        """Return the size of the file in the primary storage."""
        return self._primary_storage.size(name)

    def path(self, name: str) -> str:
        """Return the absolute path of the file in the primary storage."""
        return self._primary_storage.path(name)  # pyright: ignore[reportUnknownMemberType]

    def url(self, name: str) -> str:
        return self._primary_storage.url(name)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._primary_storage, name)
