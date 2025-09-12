from datetime import datetime

from django import template

register = template.Library()


@register.filter
def is_string(value):
    return isinstance(value, str)


@register.filter
def human_readable_permissions(perm_string):
    """
    Convert Linux file permissions to a human-readable form.
    """
    perm_map = {
        "r": "read",
        "w": "write",
        "x": "execute",
    }
    linux_perm_length = 9  # Length of a Linux file permission string

    if len(perm_string) != linux_perm_length:
        return perm_string  # Return as is if the format is unexpected

    user_perms = perm_string[0:3]
    group_perms = perm_string[3:6]
    other_perms = perm_string[6:9]

    def parse_perms(perms):
        return "+".join([perm_map[char] for char in perms if char in perm_map])

    return (
        f"User: {parse_perms(user_perms)} | "
        f"Group: {parse_perms(group_perms)} | "
        f"Others: {parse_perms(other_perms)}"
    )


@register.filter
def split(value, args):
    """
    Split a string by delimiter and return either all parts or a specific index.
    Usage:
        {{ value|split:"/" }} - returns list of all parts
        {{ value|split:"/,0" }} - returns first part
        {{ value|split:"/,-1" }} - returns last part
    """
    if not value:
        return value

    if "," in args:
        delimiter, index = args.split(",")
        try:
            index = int(index)
            return value.split(delimiter)[index]
        except (ValueError, IndexError):
            return value
    else:
        return value.split(args)


@register.filter
def parse_iso_datetime(value):
    """
    Parse an ISO datetime string and return a datetime object for Django's date filters.
    Usage: {{ value|parse_iso_datetime|date:"M j, Y" }}
    """
    if not value:
        return value

    # If it's already a datetime object, return it
    if hasattr(value, "year"):
        return value

    # If it's a string, try to parse it
    if isinstance(value, str):
        try:
            # Handle ISO format with timezone info
            if "T" in value and ("+" in value or value.endswith("Z")):
                # Parse ISO format: 2025-09-11T15:11:50.447024-04:00
                # Handle Z suffix by replacing with +00:00 for fromisoformat
                iso_value = (
                    value.replace("Z", "+00:00") if value.endswith("Z") else value
                )
                return datetime.fromisoformat(iso_value)
            # Try parsing as regular datetime string
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return value

    return value
