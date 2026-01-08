import json

from django.http import HttpRequest
from django.http import JsonResponse
from django.views import View
from loguru import logger as log

from sds_gateway.users.mixins import Auth0LoginRequiredMixin
from sds_gateway.users.utils import render_html_fragment


class RenderHTMLFragmentView(Auth0LoginRequiredMixin, View):
    """Generic view to render any HTML fragment from a Django template."""

    def post(self, request: HttpRequest) -> JsonResponse:
        """
        Render HTML fragment using server-side templates.

        Expects JSON body with:
        ```json
        {
            "template": "users/components/my_component.html",
            "context": {
                "key": "value",
                ...
            }
        }
        ```
        Returns:
            JsonResponse with rendered HTML
        """
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        template_name = data.get("template")
        context = data.get("context", {})

        if not template_name:
            return JsonResponse({"error": "Template name is required"}, status=400)

        # Security: Only allow templates from users/components/ directory
        if not template_name.startswith("users/components/"):
            log.warning(f"Invalid template path: {template_name}")
            return JsonResponse(
                {"error": "Cannot render component."},
                status=400,
            )

        try:
            html = render_html_fragment(
                template_name=template_name,
                context=context,
                request=request,
            )

            return JsonResponse({"html": html})
        except Exception as e:  # noqa: BLE001
            log.exception(f"Error rendering template {data.get('template', 'unknown')}")
            return JsonResponse({"error": str(e)}, status=500)


render_html_fragment_view = RenderHTMLFragmentView.as_view()
