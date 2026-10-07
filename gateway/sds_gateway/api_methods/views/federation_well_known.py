from __future__ import annotations

from django.http import HttpRequest
from django.http import HttpResponse
from django.http import JsonResponse
from django.views import View

from sds_gateway.api_methods.federation.well_known import build_sds_federation_document
from sds_gateway.api_methods.federation.well_known import well_known_document_ready


class SdsFederationWellKnownView(View):
    """Public site identity for federation discovery and registry domain verification."""

    def get(self, request: HttpRequest) -> HttpResponse:
        document = build_sds_federation_document()
        if not well_known_document_ready(document):
            return JsonResponse(
                {"error": "federation well-known document is not configured on this host"},
                status=503,
            )
        response = JsonResponse(document)
        response["Cache-Control"] = "no-store"
        return response


sds_federation_well_known_view = SdsFederationWellKnownView.as_view()
