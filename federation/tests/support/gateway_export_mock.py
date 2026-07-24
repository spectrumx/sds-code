"""Mock gateway federation export HTTP responses keyed by gateway host."""

from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field
from urllib.parse import urlparse

import httpx
from sds_federation.schemas.webhooks import FederatedCaptureDoc
from sds_federation.schemas.webhooks import FederatedDatasetDoc


@dataclass
class GatewayExportCatalog:
    datasets_by_host: dict[str, list[FederatedDatasetDoc]] = field(
        default_factory=dict,
    )
    captures_by_host: dict[str, list[FederatedCaptureDoc]] = field(
        default_factory=dict,
    )

    def set_datasets(
        self,
        gateway_host: str,
        docs: list[FederatedDatasetDoc],
    ) -> None:
        self.datasets_by_host[gateway_host] = docs

    def set_captures(
        self,
        gateway_host: str,
        docs: list[FederatedCaptureDoc],
    ) -> None:
        self.captures_by_host[gateway_host] = docs


def gateway_host_from_base(gateway_api_base: str) -> str:
    parsed = urlparse(str(gateway_api_base))
    return parsed.hostname or ""


def handle_gateway_export_request(  # noqa: C901, PLR0911
    request: httpx.Request,
    catalog: GatewayExportCatalog,
) -> httpx.Response | None:
    """Return a response if this request targets a mocked export URL."""
    if request.method != "GET":
        return None
    host = request.url.host
    if not host:
        return None
    path = request.url.path
    if (
        "/federation/export/datasets/" not in path
        and "/federation/export/captures/" not in path
    ):
        return None

    if "/federation/export/datasets" in path and path.rstrip("/").endswith(
        "datasets",
    ):
        docs = catalog.datasets_by_host.get(host, [])
        return httpx.Response(
            200,
            content=json.dumps([d.model_dump(mode="json") for d in docs]),
        )

    if "/federation/export/datasets/" in path:
        uuid_part = path.rstrip("/").split("/")[-1]
        for doc in catalog.datasets_by_host.get(host, []):
            if str(doc.uuid) == uuid_part:
                return httpx.Response(200, json=doc.model_dump(mode="json"))
        return httpx.Response(404, json={"detail": "not found"})

    if "/federation/export/captures" in path and path.rstrip("/").endswith(
        "captures",
    ):
        docs = catalog.captures_by_host.get(host, [])
        return httpx.Response(
            200,
            content=json.dumps([d.model_dump(mode="json") for d in docs]),
        )

    if "/federation/export/captures/" in path:
        uuid_part = path.rstrip("/").split("/")[-1]
        for doc in catalog.captures_by_host.get(host, []):
            if str(doc.uuid) == uuid_part:
                return httpx.Response(200, json=doc.model_dump(mode="json"))
        return httpx.Response(404, json={"detail": "not found"})

    return None
