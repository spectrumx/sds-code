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
        return ", ".join([perm_map[char] for char in perms if char in perm_map])

    return f"User: {parse_perms(user_perms)}, Group: {parse_perms(group_perms)}, Others: {parse_perms(other_perms)}"  # noqa: E501
