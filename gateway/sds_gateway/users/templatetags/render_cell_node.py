# gateway/sds_gateway/users/templatetags/render_cell_node.py
"""Render structured cell HTML (kind=html) with allowlists.

No |safe on raw client blobs; use this builder instead.
"""

from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import urlparse

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# --- Allowlists (tighten/extend as needed) ---
ALLOWED_TAGS = frozenset(
    {
        "a",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "i",
        "input",
        "label",
        "li",
        "p",
        "select",
        "option",
        "small",
        "span",
        "strong",
        "ul",
    }
)

# tags without end tags
VOID_TAGS = frozenset(
    {
        "input",
    }
)

# Per-tag allowed attributes (lowercase names). Omit a tag to allow only GLOBAL_ATTRS.
GLOBAL_ATTRS = frozenset(
    {
        "class",
        "id",
        "name",
        "title",
        "role",
        "aria-label",
        "aria-labelledby",
    }
)
ALLOWED_TAG_ATTRS: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "target", "rel"}),
    "input": frozenset({"type", "name", "value", "checked", "disabled"}),
    "label": frozenset({"for"}),
    "option": frozenset({"value", "selected"}),
}

_HREF_SAFE_SCHEMES = frozenset({"http", "https", "mailto", ""})


def _classes(node: dict[str, Any]) -> str | None:
    c = node.get("class")
    if c is None:
        return None
    if isinstance(c, str):
        return c.strip() or None
    if isinstance(c, list):
        return " ".join(str(x).strip() for x in c if x) or None
    return None


def _attr_allowed(tag: str, name: str) -> bool:
    n = name.lower()
    if n.startswith("on"):
        return False
    if n in GLOBAL_ATTRS:
        return True
    allowed = ALLOWED_TAG_ATTRS.get(tag)
    return n in allowed if allowed is not None else False


def _sanitize_href(value: str) -> str | None:
    v = value.strip()
    low = v.lower()
    if low.startswith(("javascript:", "data:")):
        return None
    p = urlparse(v)
    if p.scheme and p.scheme.lower() not in _HREF_SAFE_SCHEMES:
        return None
    return v


def _format_attr(tag: str, name: str, value: Any) -> str | None:  # noqa: PLR0911
    if not _attr_allowed(tag, name):
        return None
    key = name.lower()
    if key == "href" and tag == "a":
        if value is None or value is False:
            return None
        safe = _sanitize_href(str(value))
        if safe is None:
            return None
        return f' href="{escape(safe, quote=True)}"'
    if value is True:
        # Boolean attributes (e.g. checked, disabled)
        if key in ("checked", "disabled", "selected", "readonly"):
            return f" {key}"
        return None
    if value is False or value is None:
        return None
    return f' {escape(key, quote=True)}="{escape(str(value), quote=True)}"'


def _append_tag_attrs(parts: list[str], tag: str, tag_attrs: dict[str, Any]) -> None:
    for k, v in tag_attrs.items():
        if not isinstance(k, str):
            continue
        s = _format_attr(tag, k, v)
        if s:
            parts.append(s)


def _append_data_attrs(parts: list[str], data_attrs: dict[str, Any]) -> None:
    for k, v in data_attrs.items():
        if not isinstance(k, str):
            continue
        dk = f"data-{k.replace('_', '-')}"
        parts.append(f' {escape(dk, quote=True)}="{escape(str(v), quote=True)}"')


def _attrs_string(tag: str, node: dict[str, Any]) -> str:
    parts: list[str] = []

    tag_class = _classes(node)
    if tag_class and _attr_allowed(tag, "class"):
        parts.append(f' class="{escape(tag_class, quote=True)}"')

    if node.get("id") is not None and _attr_allowed(tag, "id"):
        parts.append(f' id="{escape(str(node["id"]), quote=True)}"')
    if node.get("name") is not None and _attr_allowed(tag, "name"):
        parts.append(f' name="{escape(str(node["name"]), quote=True)}"')

    tag_attrs = node.get("tag_attrs") or {}
    if isinstance(tag_attrs, dict):
        _append_tag_attrs(parts, tag, tag_attrs)

    data_attrs = node.get("data_attrs") or {}
    if isinstance(data_attrs, dict):
        _append_data_attrs(parts, data_attrs)

    return "".join(parts)


def render_html_node(node: Any) -> str:
    """Turn one schema dict into an HTML fragment; all dynamic text/attrs escaped."""
    if not isinstance(node, dict):
        return ""

    tag = (node.get("tag") or "").strip().lower()
    if not tag or tag not in ALLOWED_TAGS:
        return ""

    attrs_s = _attrs_string(tag, node)

    if tag in VOID_TAGS:
        return f"<{tag}{attrs_s} />"

    children = node.get("nested")
    inner_parts: list[str] = []
    if isinstance(children, list):
        inner_parts.extend(render_html_node(child) for child in children)

    text = node.get("text")
    if text is not None:
        inner_parts.append(escape(str(text)))

    inner = "".join(inner_parts)
    return f"<{tag}{attrs_s}>{inner}</{tag}>"


@register.simple_tag
def render_cell_node(node: Any) -> str:
    """
    Render a structured HTML cell node (e.g. kind \"html\" payloads).

    Safe for use without |safe: output is built from allowlisted tags/attrs and
    escaped text/values.
    """
    return mark_safe(render_html_node(node))  # noqa: S308 — allowlist-built HTML only
