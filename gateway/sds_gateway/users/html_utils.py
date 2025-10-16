"""
Django HTML Rendering Utilities
Provides server-side HTML generation with built-in XSS protection via Django templates.

This module provides secure server-side rendering for any content containing server data.
All HTML is rendered using Django templates with automatic XSS protection.

Usage:
    from sds_gateway.users.html_utils import render_html_fragment

    # In a Django view
    html = render_html_fragment(
        "users/components/my_component.html",
        {"data": my_data},
        request
    )
    return JsonResponse({"html": html})
    
    # Client-side JavaScript calls generic endpoint
    const response = await window.APIClient.post("/users/render-html/", {
        template: "users/components/my_component.html",
        context: { data: normalizedData }
    });
    container.innerHTML = response.html;  // Safe!
"""

from typing import Any

from django.http import HttpRequest  # type: ignore
from django.template.loader import render_to_string  # type: ignore


def render_html_fragment(
    template_name: str,
    context: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> str:
    """
    Render HTML fragment from Django template with automatic XSS protection.
    
    This is the primary function for server-side HTML rendering. It provides:
    - Automatic XSS protection via Django template auto-escaping
    - Request context for template tags that need it
    - Simple, generic interface for any template
    
    Args:
        template_name: Path to Django template (e.g., "users/components/my_component.html")
        context: Dictionary of variables to pass to the template
        request: HttpRequest object for context processors (optional)
        
    Returns:
        Safe HTML string with all user data automatically escaped
        
    Example:
        >>> html = render_html_fragment(
        ...     "users/components/user_chips.html",
        ...     {
        ...         "users": [{"name": "John", "email": "john@example.com"}],
        ...         "show_permission_select": True
        ...     },
        ...     request
        ... )
        >>> return JsonResponse({"html": html})
        
    Security:
        Django templates automatically escape all variable output unless explicitly
        marked as safe with |safe filter. This protects against XSS attacks.
    """
    full_context = context or {}
    if request:
        full_context["request"] = request
    return render_to_string(template_name, full_context)

