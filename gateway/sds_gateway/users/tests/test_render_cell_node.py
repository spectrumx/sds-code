"""Tests for render_cell_node templatetag and render_html_node."""

import pytest
from django.template import Context
from django.template import Template

from sds_gateway.users.templatetags.render_cell_node import render_html_node


@pytest.mark.parametrize(
    ("node", "expected_substring"),
    [
        (
            {"tag": "span", "class": "badge bg-success", "text": "OK"},
            '<span class="badge bg-success">OK</span>',
        ),
        (
            {
                "tag": "div",
                "class": "row",
                "nested": [
                    {"tag": "span", "class": "text-muted", "text": "nested"},
                ],
            },
            '<div class="row"><span class="text-muted">nested</span></div>',
        ),
    ],
)
def test_render_html_node_allowed_markup(node: dict, expected_substring: str) -> None:
    assert render_html_node(node) == expected_substring


def test_render_html_node_escapes_text() -> None:
    out = render_html_node(
        {"tag": "span", "text": "<script>alert(1)</script>"},
    )
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_render_html_node_drops_disallowed_child_tag() -> None:
    out = render_html_node(
        {
            "tag": "div",
            "nested": [
                {"tag": "script", "text": "alert(1)"},
                {"tag": "span", "text": "safe"},
            ],
        },
    )
    assert "<script" not in out
    assert "safe" in out


def test_render_html_node_void_input() -> None:
    out = render_html_node(
        {
            "tag": "input",
            "tag_attrs": {"type": "checkbox", "name": "c", "value": "1"},
        },
    )
    assert out.startswith("<input ")
    assert out.endswith(" />")
    assert 'type="checkbox"' in out


def test_render_html_node_strips_javascript_href() -> None:
    out = render_html_node(
        {
            "tag": "a",
            "tag_attrs": {"href": "javascript:alert(1)"},
            "text": "x",
        },
    )
    assert "javascript:" not in out
    assert "href=" not in out


def test_render_cell_node_template_tag() -> None:
    tpl = Template("{% load render_cell_node %}{% render_cell_node cell %}")
    html = tpl.render(
        Context(
            {
                "cell": {
                    "tag": "span",
                    "class": "badge",
                    "text": "y",
                },
            },
        ),
    )
    assert html.strip() == '<span class="badge">y</span>'
