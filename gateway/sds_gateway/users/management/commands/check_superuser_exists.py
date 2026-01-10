"""Django management command to check for an existing superuser."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Output "yes" if any superuser exists, otherwise "no".

    Used during automated deployment to check if superuser creation is needed.
    """

    help = "Report whether a superuser exists (yes/no)."

    def handle(self, *args, **options) -> None:
        """Write the superuser existence result to stdout."""
        user_model = get_user_model()
        has_superuser = user_model.objects.filter(is_superuser=True).exists()
        response = "yes" if has_superuser else "no"
        self.stdout.write(response)
