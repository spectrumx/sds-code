"""Drop unused ``verified`` status from unique FQDN constraint."""

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("api_methods", "0023_registry_application_service_urls_charfield"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="registryapplication",
            name="unique_active_registry_application_per_fqdn",
        ),
        migrations.AddConstraint(
            model_name="registryapplication",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    (
                        "status__in",
                        [
                            "pending_verification",
                            "verification_failed",
                            "pending_approval",
                            "approved",
                        ],
                    ),
                ),
                fields=("fqdn",),
                name="unique_active_registry_application_per_fqdn",
            ),
        ),
    ]
