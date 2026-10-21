from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("api_methods", "0022_registry_application"),
    ]

    operations = [
        migrations.AlterField(
            model_name="registryapplication",
            name="gateway_api_base",
            field=models.CharField(
                blank=True,
                help_text="Applicant gateway API base (may use internal Docker hostnames in lab).",
                max_length=512,
            ),
        ),
        migrations.AlterField(
            model_name="registryapplication",
            name="sync_service_url",
            field=models.CharField(
                blank=True,
                help_text="Applicant federation sync base URL.",
                max_length=512,
            ),
        ),
    ]
