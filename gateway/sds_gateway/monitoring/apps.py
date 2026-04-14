from django.apps import AppConfig


class MonitoringConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sds_gateway.monitoring"
    verbose_name = "Monitoring"
