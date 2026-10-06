# Generated manually for RegistryApplication

import datetime
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations
from django.db import models
from django.utils import timezone


def _default_registry_challenge_expires_at() -> datetime.datetime:
    return timezone.now() + datetime.timedelta(hours=72)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("api_methods", "0021_dataset_previous_version_alter_dataset_version"),
    ]

    operations = [
        migrations.CreateModel(
            name="RegistryApplication",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("is_deleted", models.BooleanField(default=False)),
                ("is_public", models.BooleanField(default=False)),
                ("fqdn", models.CharField(db_index=True, max_length=255)),
                ("display_name", models.CharField(max_length=255)),
                (
                    "contact_email",
                    models.EmailField(
                        blank=True,
                        help_text="Optional ops contact; defaults to contact user's email when empty.",
                        max_length=254,
                    ),
                ),
                (
                    "proposed_site_name",
                    models.CharField(
                        blank=True,
                        help_text="Applicant-suggested short site id (federation.toml [site].name).",
                        max_length=64,
                    ),
                ),
                (
                    "site_name",
                    models.CharField(
                        blank=True,
                        help_text="Assigned on approval; must be unique in the signed manifest.",
                        max_length=64,
                    ),
                ),
                ("gateway_api_base", models.URLField(blank=True, max_length=512)),
                ("sync_service_url", models.URLField(blank=True, max_length=512)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending_verification", "Pending Verification"),
                            ("verification_failed", "Verification Failed"),
                            ("verified", "Verified"),
                            ("pending_approval", "Pending Approval"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("withdrawn", "Withdrawn"),
                            ("published", "Published"),
                        ],
                        db_index=True,
                        default="pending_verification",
                        max_length=32,
                    ),
                ),
                ("challenge_token_hash", models.CharField(max_length=64)),
                (
                    "challenge_expires_at",
                    models.DateTimeField(
                        default=_default_registry_challenge_expires_at,
                    ),
                ),
                (
                    "challenge_method",
                    models.CharField(
                        choices=[
                            ("well_known_json", "Well Known Json"),
                            ("well_known_path", "Well Known Path"),
                        ],
                        default="well_known_json",
                        max_length=32,
                    ),
                ),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                (
                    "verified_well_known",
                    models.JSONField(
                        blank=True,
                        help_text="Snapshot of /.well-known/sds-federation.json at successful verify.",
                        null=True,
                    ),
                ),
                ("verification_attempts", models.PositiveSmallIntegerField(default=0)),
                ("last_verification_error", models.TextField(blank=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("rejected_reason", models.TextField(blank=True)),
                ("withdrawn_at", models.DateTimeField(blank=True, null=True)),
                (
                    "published_manifest_serial",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                (
                    "ca_cert_file",
                    models.CharField(
                        blank=True,
                        help_text="Basename only; distributed via signed manifest.",
                        max_length=255,
                    ),
                ),
                ("client_cert_fingerprints", models.JSONField(blank=True, null=True)),
                (
                    "contact",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="registry_applications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_registry_applications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddIndex(
            model_name="registryapplication",
            index=models.Index(
                fields=["status", "fqdn"],
                name="api_methods_status_fqdn_idx",
            ),
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
                            "verified",
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
