"""Data migration: add each ShareGroup owner as a member of their own group."""

from django.db import migrations


def add_owners_as_members(apps, schema_editor):
    ShareGroup = apps.get_model("api_methods", "ShareGroup")
    for group in ShareGroup.objects.filter(is_deleted=False).select_related("owner"):
        group.members.add(group.owner)


def remove_owners_as_members(apps, schema_editor):
    """Reverse: remove owners who are members solely because of this migration.

    This is a best-effort reverse — it removes the owner from members for
    every non-deleted group.  Owners who were added manually before this
    migration was applied will also be removed, but that is an acceptable
    trade-off for a reversible migration.
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
    ]
