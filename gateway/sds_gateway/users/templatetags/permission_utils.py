from django import template

from sds_gateway.api_methods.models import PermissionLevel

register = template.Library()


@register.filter
def permission_icon(level: PermissionLevel):
    """Get the Bootstrap icon class for a permission level."""
    icons = {
        PermissionLevel.OWNER: "bi-person-check",
        PermissionLevel.CO_OWNER: "bi-gear",
        PermissionLevel.CONTRIBUTOR: "bi-plus-circle",
        PermissionLevel.VIEWER: "bi-eye",
    }
    return icons.get(level, "bi-question-circle")


@register.filter
def permission_badge_class(level):
    """Get the Bootstrap badge class for a permission level."""
    badge_classes = {
        PermissionLevel.OWNER: "bg-owner",
        PermissionLevel.CO_OWNER: "bg-co-owner",
        PermissionLevel.CONTRIBUTOR: "bg-contributor",
        PermissionLevel.VIEWER: "bg-viewer",
    }
    return badge_classes.get(level, "bg-secondary")
