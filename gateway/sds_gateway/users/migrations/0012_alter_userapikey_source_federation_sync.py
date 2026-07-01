# Generated manually for FederationSync API key source

from django.db import migrations, models

import sds_gateway.api_methods.models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0011_user_orcid_id_alter_user_is_approved"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userapikey",
            name="source",
            field=models.CharField(
                choices=[
                    (sds_gateway.api_methods.models.KeySources["SDSWebUI"], "SDS Web UI"),
                    (
                        sds_gateway.api_methods.models.KeySources["SVIBackend"],
                        "SVI Backend",
                    ),
                    (
                        sds_gateway.api_methods.models.KeySources["SVIWebUI"],
                        "SVI Web UI",
                    ),
                    (
                        sds_gateway.api_methods.models.KeySources["FederationSync"],
                        "Federation Sync",
                    ),
                ],
                default=sds_gateway.api_methods.models.KeySources["SDSWebUI"],
                max_length=255,
            ),
        ),
    ]
