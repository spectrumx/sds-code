"""Template filters for cache-busting static assets."""

import json
import os
from pathlib import Path

from django import template
from django.templatetags.static import static

register = template.Library()


def _commit_hash() -> str:
    """Return the current commit hash for cache-busting."""
    # Try version.json first (shipped by CI/CD)
    version_path = Path(__file__).parent.parent.parent.parent / "version.json"
    if version_path.is_file():
        try:
            data = json.loads(version_path.read_text())
            return data.get("commit", "")
        except (OSError, json.JSONDecodeError):
            pass

    return os.environ.get("SDS_COMMIT_HASH", "")


@register.simple_tag(takes_context=False)
def cache_bust(url: str) -> str:
    """Append a cache-busting query parameter to a static asset URL.

    Usage:
        {% load cache_busting %}
        <link rel="stylesheet" href="{% cache_bust '/static/css/app.css' %}" />

    The query parameter value is a git commit hash that changes on every deploy,
    forcing browsers and CDNs to fetch fresh assets.
    """
    if not url:
        return url

    # Only bust {% static %} URLs, not CDN links
    if url.startswith("/static/"):
        version = _commit_hash()
        if version and version != "unknown":
            sep = "&" if "?" in url else "?"
            return f"{url}{sep}v={version}"

    return url


@register.simple_tag(takes_context=False)
def static_bust(name: str) -> str:
    """Cache-busting wrapper around the built-in {% static %} tag.

    Usage:
        {% load cache_busting %}
        <link rel="stylesheet" href="{% static_bust 'css/app.css' %}" />
    """
    url = static(name)
    return cache_bust(url)
