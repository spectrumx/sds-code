from __future__ import annotations

from django.http import HttpRequest
from django.http import HttpResponse
from django.http import HttpResponseNotFound
from django.views import View

from sds_gateway.api_methods.federation.registry_manifest_publish import (
    read_published_manifest_bytes,
)
from sds_gateway.api_methods.federation.registry_manifest_publish import (
    read_published_signature_bytes,
)


class SdsRegistryManifestView(View):
    """Signed federation membership list (mothership only)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        payload = read_published_manifest_bytes()
        if payload is None:
            return HttpResponseNotFound("registry manifest not published")
        response = HttpResponse(payload, content_type="application/json")
        response["Cache-Control"] = "public, max-age=60"
        return response


class SdsRegistryManifestSignatureView(View):
    """Base64 Ed25519 signature over the raw sites.json bytes."""

    def get(self, request: HttpRequest) -> HttpResponse:
        signature = read_published_signature_bytes()
        if signature is None:
            return HttpResponseNotFound("registry manifest signature not published")
        response = HttpResponse(signature, content_type="text/plain; charset=utf-8")
        response["Cache-Control"] = "public, max-age=60"
        return response


sds_registry_manifest_view = SdsRegistryManifestView.as_view()
sds_registry_manifest_signature_view = SdsRegistryManifestSignatureView.as_view()
