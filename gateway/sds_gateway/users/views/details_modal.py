"""HTTP views for asset details modal HTML fragments."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

from django.http import Http404
from django.http import JsonResponse
from django.views import View

from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.views.details_modal_registry import DETAILS_MODAL_JSON_BUILDERS
from sds_gateway.users.views.details_modal_registry import DETAILS_MODAL_REGISTRY
from sds_gateway.users.views.details_modal_registry import render_details_modal_body


class DetailsModalFragmentView(Auth0LoginRequiredMixin, View):
    """GET /users/details-modal/<asset_type>/<uuid>/ → JSON { html, title, meta }."""

    def dispatch(self, request, *args, **kwargs):
        # Public published datasets: allow anonymous JSON/HTML fragment
        # (access in registry).
        if kwargs.get("asset_type") == "dataset":
            return View.dispatch(self, request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)

    def get(
        self, request, asset_type: str, uuid: UUID, *args, **kwargs
    ) -> JsonResponse:
        builder = DETAILS_MODAL_REGISTRY.get(asset_type)
        json_builder = DETAILS_MODAL_JSON_BUILDERS.get(asset_type)
        if builder is None or json_builder is None:
            _unknown_asset_type = "Unknown asset type"
            raise Http404(_unknown_asset_type)

        ctx = builder(request, uuid)
        if ctx is None:
            _builder_not_found = "Not found"
            raise Http404(_builder_not_found)

        html = render_details_modal_body(request, asset_type, ctx)
        if not html:
            _html_not_found = "Not found"
            raise Http404(_html_not_found)

        return JsonResponse(json_builder(ctx, html))


details_modal_fragment_view = DetailsModalFragmentView.as_view()
