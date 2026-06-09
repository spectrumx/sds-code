"""Object storage client facade for SeaweedFS + MinIO migration."""

import hashlib
import logging
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from minio import Minio

from .storage_errors import is_missing_object_error as _is_missing_object_error

log = logging.getLogger(__name__)

_BUCKET_NAME_POSITION = 0
_OBJECT_NAME_POSITION = 1
_BUCKET_AND_OBJECT_ARGUMENT_COUNT = 2


def _normalize_endpoint(endpoint: str) -> str:
    """Convert endpoint URL to host:port format accepted by MinIO client."""
    parsed_endpoint = urlparse(endpoint)
    if parsed_endpoint.netloc:
        return parsed_endpoint.netloc
    return endpoint


def _safe_object_reference(object_name: Any) -> str:
    """Return a non-reversible identifier suitable for operational logs."""
    object_name_text = str(object_name)
    object_name_digest = hashlib.sha256(object_name_text.encode()).hexdigest()[:12]
    return f"sha256={object_name_digest} len={len(object_name_text)}"


def _build_minio_client(
    *,
    endpoint: str,
    access_key: str,
    secret_key: str,
    secure: bool,
) -> Minio:
    """Build a MinIO API-compatible client."""
    return Minio(
        _normalize_endpoint(endpoint),
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
    )


class ObjectStoreFacade:
    """Facade exposing MinIO-compatible methods with primary/fallback behavior.

    It encapsulates two storage clients (primary and secondary) and provides
    methods that implement the desired read/write behavior based on
    configuration flags. The facade also handles argument rewriting to target
    the correct buckets for each store and provides safe object references
    for logging.
    """

    def __init__(
        self,
        *,
        primary_client: Minio,
        secondary_client: Minio | None,
        read_fallback_to_secondary_enabled: bool,
        write_both_enabled: bool,
        dual_write_strict: bool,
    ) -> None:
        """Initialize the ObjectStoreFacade with given clients and behavior flags.

        Args:
            primary_client:     MinIO client for the primary object store (SeaweedFS).
            secondary_client:   MinIO client for the secondary object store (secondary),
                                or None when only the primary store is configured.
            read_fallback_to_secondary_enabled: Whether to fallback to secondary on
                read errors.
            write_both_enabled: Whether to perform writes on both stores.
            dual_write_strict:  Requires both writes to succeed, raises otherwise.
        """
        self._primary_client = primary_client
        self._secondary_client = secondary_client
        self._read_fallback_to_secondary_enabled = read_fallback_to_secondary_enabled
        self._write_both_enabled = write_both_enabled
        self._dual_write_strict = dual_write_strict

    def _rewrite_bucket_name(
        self,
        bucket_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        """Return arguments rewritten for the target store bucket."""
        rewritten_args = list(args)
        rewritten_kwargs = dict(kwargs)

        if "bucket_name" in rewritten_kwargs or not rewritten_args:
            rewritten_kwargs["bucket_name"] = bucket_name
        else:
            rewritten_args[0] = bucket_name

        return tuple(rewritten_args), rewritten_kwargs

    def _primary_call_arguments(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        """Build call arguments targeting the primary object-store bucket."""
        kwargs.pop("bucket_name", None)
        return self._rewrite_bucket_name(
            settings.PRIMARY_STORAGE_BUCKET_NAME,
            *args,
            **kwargs,
        )

    def _secondary_call_arguments(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        """Build call arguments targeting the secondary object-store bucket."""
        kwargs.pop("bucket_name", None)
        return self._rewrite_bucket_name(
            settings.SECONDARY_STORAGE_BUCKET_NAME,
            *args,
            **kwargs,
        )

    def _object_reference(self, *args: Any, **kwargs: Any) -> str:
        """Return a safe object identifier for logs."""
        object_name = kwargs.get("object_name")
        if object_name is None:
            if len(args) >= _BUCKET_AND_OBJECT_ARGUMENT_COUNT:
                object_name = args[_OBJECT_NAME_POSITION]
            elif args and "bucket_name" not in kwargs:
                object_name = args[_BUCKET_NAME_POSITION]
            else:
                object_name = "unknown"

        return _safe_object_reference(object_name)

    def _read_with_optional_fallback(
        self,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        primary_method = getattr(self._primary_client, method_name)
        primary_args, primary_kwargs = self._primary_call_arguments(*args, **kwargs)
        try:
            return primary_method(*primary_args, **primary_kwargs)
        except Exception as error:
            if not self._read_fallback_to_secondary_enabled:
                raise
            if not _is_missing_object_error(error):
                raise
            if not self._secondary_client:
                raise

            log.warning(
                "Object %s not found in primary store, falling back to secondary",
                self._object_reference(*args, **kwargs),
            )
            secondary_method = getattr(self._secondary_client, method_name)
            secondary_args, secondary_kwargs = self._secondary_call_arguments(
                *args,
                **kwargs,
            )
            return secondary_method(*secondary_args, **secondary_kwargs)

    def _write_with_optional_dual_write(
        self,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        primary_method = getattr(self._primary_client, method_name)
        primary_args, primary_kwargs = self._primary_call_arguments(*args, **kwargs)
        primary_result = primary_method(*primary_args, **primary_kwargs)

        if not self._write_both_enabled or not self._secondary_client:
            return primary_result

        secondary_method = getattr(self._secondary_client, method_name)
        secondary_args, secondary_kwargs = self._secondary_call_arguments(
            *args,
            **kwargs,
        )
        try:
            secondary_method(*secondary_args, **secondary_kwargs)
        except Exception:
            if self._dual_write_strict:
                raise

            log.exception(
                "Secondary object-store write failed in non-strict dual-write mode"
            )

        return primary_result

    def _delete_from_both_stores(self, *args: Any, **kwargs: Any) -> Any:
        """Delete from primary and, when needed, from secondary store too."""
        primary_args, primary_kwargs = self._primary_call_arguments(*args, **kwargs)
        primary_result = self._primary_client.remove_object(
            *primary_args,
            **primary_kwargs,
        )

        if not self._secondary_client or not (
            self._write_both_enabled or self._read_fallback_to_secondary_enabled
        ):
            return primary_result

        secondary_args, secondary_kwargs = self._secondary_call_arguments(
            *args,
            **kwargs,
        )
        try:
            self._secondary_client.remove_object(*secondary_args, **secondary_kwargs)
        except Exception:
            if self._read_fallback_to_secondary_enabled or self._dual_write_strict:
                raise

            log.exception(
                "Secondary object-store delete failed in non-strict dual-write mode"
            )

        return primary_result

    def get_object(self, *args: Any, **kwargs: Any) -> Any:
        """Get object stream from primary store with optional fallback."""
        return self._read_with_optional_fallback("get_object", *args, **kwargs)

    def fget_object(self, *args: Any, **kwargs: Any) -> Any:
        """Download object to local file from primary store with optional fallback."""
        return self._read_with_optional_fallback("fget_object", *args, **kwargs)

    def put_object(self, *args: Any, **kwargs: Any) -> Any:
        """Upload object from stream with optional dual-write behavior."""
        return self._write_with_optional_dual_write("put_object", *args, **kwargs)

    def fput_object(self, *args: Any, **kwargs: Any) -> Any:
        """Upload object from local file with optional dual-write behavior."""
        return self._write_with_optional_dual_write("fput_object", *args, **kwargs)

    def remove_object(self, *args: Any, **kwargs: Any) -> Any:
        """Remove object from primary store with optional dual-write behavior."""
        return self._delete_from_both_stores(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown methods to the primary client for compatibility."""
        return getattr(self._primary_client, name)


def _is_secondary_configured() -> bool:
    """Return True when a secondary object store is explicitly configured."""
    return getattr(settings, "SECONDARY_ACCESS_KEY_ID", None) != getattr(
        settings, "LEGACY_AWS_ACCESS_KEY_ID", None
    )


def get_minio_client() -> ObjectStoreFacade:
    """Return migration-aware object store facade while keeping API name stable."""
    primary_client = _build_minio_client(
        endpoint=settings.PRIMARY_ENDPOINT_URL,
        access_key=settings.PRIMARY_ACCESS_KEY_ID,
        secret_key=settings.PRIMARY_SECRET_ACCESS_KEY,
        secure=settings.PRIMARY_STORAGE_USE_HTTPS,
    )

    if _is_secondary_configured():
        secondary_client = _build_minio_client(
            endpoint=settings.SECONDARY_ENDPOINT_URL,
            access_key=settings.SECONDARY_ACCESS_KEY_ID,
            secret_key=settings.SECONDARY_SECRET_ACCESS_KEY,
            secure=settings.SECONDARY_STORAGE_USE_HTTPS,
        )
    else:
        secondary_client = None  # type: ignore[assignment]

    return ObjectStoreFacade(
        primary_client=primary_client,
        secondary_client=secondary_client,
        read_fallback_to_secondary_enabled=(
            settings.OBJECT_STORE_READ_FALLBACK_TO_SECONDARY_ENABLED
        ),
        write_both_enabled=settings.OBJECT_STORE_WRITE_BOTH_ENABLED,
        dual_write_strict=settings.OBJECT_STORE_DUAL_WRITE_STRICT,
    )
