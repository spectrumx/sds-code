import json
from pathlib import Path

from django.http import HttpRequest
from django.http import JsonResponse
from django.views import View
from loguru import logger as log

from sds_gateway.users.utils import render_html_fragment


def _is_safe_template_path(template_name: str) -> bool:
    """Check if the template path is safe (within users/components/)."""
    normalized_path = Path(template_name).resolve()
    base_dir = Path("users/components").resolve()
    try:
        normalized_path.relative_to(base_dir)
    except ValueError:
        return False
    else:
        return True


# Auth0LoginRequiredMixin is not used because this view might be called from the home
# page where users may not be authenticated, but we still want to allow rendering of
# public components.
#
# SECURITY MODEL:
# - Only templates in users/components/ directory are allowed (enforced by prefix check)
# - Context is provided by the client JSON body
# - Normal template variables use HTML escaping; |safe or raw HTML must not trust
#   client strings unless sanitized or rendered via allowlisted builders (e.g. render_cell_node)
# - CSRF protection is still enforced by Django middleware
# - No sensitive server-side data is exposed - only client-provided data is rendered
# - Calling views (e.g., DatasetDetailsView) are responsible for authorization checks
# - Rate limiting should be configured at the infrastructure level
class RenderHTMLFragmentView(View):
    """Generic view to render any HTML fragment from a Django template.

    This endpoint allows rendering of component templates with client-provided context.
    It's designed to support both authenticated and unauthenticated users for rendering
    public UI components (e.g., file trees for public datasets).

    Security:
    - Restricted to users/components/ templates only
    - Context is client-provided (no database queries in this view)
    - Escaping applies to normal variables; components using |safe need careful design
    - Authorization must be handled by calling views
    """

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
        # Resolves path traversal attempts like "../"
        if not _is_safe_template_path(template_name):
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
        except Exception:  # noqa: BLE001
            log.exception(f"Error rendering template {data.get('template', 'unknown')}")
            return JsonResponse(
                {"error": "Failed to render component.", "code": "RENDER_ERROR"},
                status=500,
            )


render_html_fragment_view = RenderHTMLFragmentView.as_view()
