"""Database filters for dataset file manifest (download) listings."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from django.db.models import Q
from django.db.models import QuerySet

if TYPE_CHECKING:
    from rest_framework.request import Request

    from sds_gateway.api_methods.models import File


def normalize_top_level_dir_prefix(raw: str) -> str:
    """Normalize a capture ``top_level_dir`` / path prefix for URL and DB matching."""
    s = raw.strip().replace("\\", "/")
    if not s.startswith("/"):
        s = f"/{s}"
    return s.rstrip("/") or "/"


def parse_capture_uuid_query(request: Request) -> list[UUID]:
    """Parse ``capture`` query params (repeat or comma-separated) into UUIDs."""
    vals: list[str] = []
    for item in request.query_params.getlist("capture"):
        vals.extend(p.strip() for p in item.split(",") if p.strip())
    out: list[UUID] = []
    for s in vals:
        try:
            out.append(UUID(s))
        except ValueError as err:
            msg = f"Invalid capture UUID: {s!r}"
            raise ValueError(msg) from err
    return out


def parse_top_level_dir_query(request: Request) -> list[str]:
    """Parse ``top_level_dir`` query params into normalized path prefixes."""
    vals: list[str] = []
    for item in request.query_params.getlist("top_level_dir"):
        vals.extend(p.strip() for p in item.split(",") if p.strip())
    return [normalize_top_level_dir_prefix(v) for v in vals]


def filter_dataset_files_queryset(
    qs: QuerySet[File],
    *,
    capture_uuids: list[UUID],
    top_level_dir_prefixes: list[str],
) -> QuerySet[File]:
    """Restrict manifest files; capture UUID and path filters are OR-ed (SDK parity)."""
    if not capture_uuids and not top_level_dir_prefixes:
        return qs
    parts: list[Q] = []
    if capture_uuids:
        parts.append(
            Q(captures__uuid__in=capture_uuids) | Q(capture__uuid__in=capture_uuids)
        )
    if top_level_dir_prefixes:
        qd = Q()
        for pre in top_level_dir_prefixes:
            qd |= Q(directory=pre) | Q(directory__startswith=f"{pre}/")
        parts.append(qd)
    q = parts[0] if len(parts) == 1 else parts[0] | parts[1]
    return qs.filter(q).distinct()
