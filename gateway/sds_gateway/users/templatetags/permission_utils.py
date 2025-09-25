from django import template

register = template.Library()


@register.filter
def permission_icon(level):
    """Get the Bootstrap icon class for a permission level."""
    icons = {
        "owner": "bi-person-check",
        "co-owner": "bi-gear",
        "contributor": "bi-plus-circle",
        "viewer": "bi-eye",
        "remove": "bi-person-slash",
    }
    return icons.get(level, "bi-question-circle")


@register.filter
def permission_badge_class(level):
    """Get the Bootstrap badge class for a permission level."""
    badge_classes = {
        "owner": "bg-owner",
        "co-owner": "bg-co-owner",
        "contributor": "bg-contributor",
        "viewer": "bg-viewer",
    }
    return badge_classes.get(level, "bg-secondary")
