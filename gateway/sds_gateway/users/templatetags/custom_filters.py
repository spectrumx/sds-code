from django import template

register = template.Library()


@register.filter
def is_string(value):
    return isinstance(value, str)
