from django.conf import settings
from django.contrib.sites.apps import SitesConfig as DjangoSitesConfig
from django.db.models.signals import post_migrate


# This signal exists to fix a production incident (2026-07-31):
# Auth0 login returned SocialApp.DoesNotExist because the Site record
# (id=SITE_ID) had a hardcoded domain from migration 0003 that didn't
# match the deployment's actual domain.  django-allauth's on_site()
# queries the SocialApp by request site, so the mismatch caused the
# lookup to fail.  We now sync the Site domain from settings on every
# migrate instead of relying on a one-shot hardcoded migration.
def ensure_site_record(sender, **kwargs):
    """Post-migrate handler: ensure Site(id=SITE_ID) matches configured SITE_DOMAIN.

    Runs after every migration (including deployment). Idempotent — if the
    domain already matches, no change. If the record was deleted or the env
    changed, it corrects the entry and keeps the DB sequence in sync.
    """
    from django.contrib.sites.models import Site
    from django.db import connection

    domain = settings.SITE_DOMAIN
    name = getattr(settings, "SDS_BRANDED_SITE_NAME", "SpectrumX Data System Gateway")

    _site, created = Site.objects.update_or_create(
        id=settings.SITE_ID,
        defaults={"domain": domain, "name": name},
    )

    if created and connection.vendor == "postgresql":
        # We provided the ID explicitly, so the DB sequence for auto-generated
        # IDs is now stale. Fix it to avoid a unique-constraint violation the
        # next time a Site is created without an explicit ID. PostgreSQL only —
        # SQLite does not use sequences.
        newest = Site.objects.order_by("-id").first()
        if newest is None:
            return  # should never happen — we just created one
        max_id = newest.id
        with connection.cursor() as cursor:
            cursor.execute("SELECT last_value from django_site_id_seq")
            row = cursor.fetchone()
            if row is None:
                return
            current_id = row[0]
            if current_id <= max_id:
                cursor.execute(
                    "alter sequence django_site_id_seq restart with %s",
                    [max_id + 1],
                )


class SitesConfig(DjangoSitesConfig):
    def ready(self):
        super().ready()
        post_migrate.connect(ensure_site_record, sender=self)
