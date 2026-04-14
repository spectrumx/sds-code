from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("monitoring", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicecheck",
            name="host",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="servicecheck",
            name="port",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
