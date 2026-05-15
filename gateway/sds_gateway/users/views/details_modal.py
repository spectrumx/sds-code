"""HTTP views for asset details modal HTML fragments."""

from __future__ import annotations

from uuid import UUID

from django.http import Http404
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views import View

from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.views.details_modal_registry import CAPTURE_FILES_SUMMARY_TEMPLATE
from sds_gateway.users.views.details_modal_registry import DETAILS_MODAL_JSON_BUILDERS
from sds_gateway.users.views.details_modal_registry import DETAILS_MODAL_REGISTRY
from sds_gateway.users.views.details_modal_registry import build_capture_files_summary_context
from sds_gateway.users.views.details_modal_registry import render_details_modal_body


class DetailsModalFragmentView(Auth0LoginRequiredMixin, View):
    """GET /users/details-modal/<asset_type>/<uuid>/ → JSON { html, title, meta }."""

    def dispatch(self, request, *args, **kwargs):
        # Public published datasets: allow anonymous JSON/HTML fragment (access in registry).
        if kwargs.get("asset_type") == "dataset":
            return View.dispatch(self, request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, asset_type: str, uuid: UUID, *args, **kwargs) -> JsonResponse:
        if request.GET.get("fragment") == "files":
            if asset_type != "capture":
                raise Http404("Unknown fragment")
            ctx = build_capture_files_summary_context(request, uuid)
            if ctx is None:
                raise Http404("Not found")
            html = render_to_string(
                CAPTURE_FILES_SUMMARY_TEMPLATE,
                ctx,
                request=request,
            )
            return JsonResponse({"html": html})

        builder = DETAILS_MODAL_REGISTRY.get(asset_type)
        json_builder = DETAILS_MODAL_JSON_BUILDERS.get(asset_type)
        if builder is None or json_builder is None:
            raise Http404("Unknown asset type")

        ctx = builder(request, uuid)
        if ctx is None:
            raise Http404("Not found")

        html = render_details_modal_body(request, asset_type, ctx)
        if not html:
            raise Http404("Not found")

        return JsonResponse(json_builder(ctx, html))


details_modal_fragment_view = DetailsModalFragmentView.as_view()
