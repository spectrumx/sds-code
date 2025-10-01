"""Custom validators for the users app."""

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_orcid_id(value):
    """Validate the ORCID ID format."""
    if not value:
        return value

    if not re.match(r"^\d{4}-\d{4}-\d{4}-\d{4}$", value):
        raise ValidationError(_("ORCID ID must be in the format 0000-0000-0000-0000."))

    return value
