from django.apps import AppConfig


class ApiMethodsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sds_gateway.api_methods"

    def ready(self):
        import sds_gateway.api_methods.schema  # noqa: F401
