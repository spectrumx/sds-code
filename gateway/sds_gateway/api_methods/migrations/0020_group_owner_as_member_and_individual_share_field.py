"""Add each ShareGroup owner as a member of their own group; add is_individual_share to UserSharePermission.

Existing UserSharePermission rows default to True (individual share), preserving all
current access. Permissions created purely through a group share are written with
False so that revoking the group also revokes the permission.
"""

from django.db import migrations
from django.db import models


def add_owners_as_members(apps, schema_editor):
    ShareGroup = apps.get_model("api_methods", "ShareGroup")
    for group in ShareGroup.objects.filter(is_deleted=False).select_related("owner"):
        group.members.add(group.owner)


def remove_owners_as_members(apps, schema_editor):
    """Reverse: remove owners who are members solely because of this migration.

    Best-effort — also removes owners added manually before this migration, which
    is an acceptable trade-off for a reversible migration.
    """
    ShareGroup = apps.get_model("api_methods", "ShareGroup")
    for group in ShareGroup.objects.filter(is_deleted=False).select_related("owner"):
        group.members.remove(group.owner)


class Migration(migrations.Migration):
    dependencies = [
        ("api_methods", "0019_capture_datasets_file_captures_file_datasets_and_more"),
    ]

    operations = [
        migrations.RunPython(add_owners_as_members, remove_owners_as_members),
        migrations.AddField(
            model_name="usersharepermission",
            name="is_individual_share",
            field=models.BooleanField(default=True),
        ),
    ]
