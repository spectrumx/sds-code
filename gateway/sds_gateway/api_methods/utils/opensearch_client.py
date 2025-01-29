from django.conf import settings
from opensearchpy import OpenSearch
from opensearchpy.connection.http_urllib3 import Urllib3HttpConnection


def get_opensearch_client():
    """Get an OpenSearch client with proper SSL configuration.

    The client is configured based on Django settings, with proper SSL handling
    for both development and production environments.
    """
    client_kwargs = {
        "hosts": [{"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}],
        "http_auth": (settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
        "use_ssl": settings.OPENSEARCH_USE_SSL,
        "verify_certs": settings.OPENSEARCH_VERIFY_CERTS,
        "connection_class": Urllib3HttpConnection,
    }

    # Only add SSL-specific settings if SSL is enabled
    if settings.OPENSEARCH_USE_SSL:
        client_kwargs.update(
            {
                "ssl_assert_hostname": True,
                "ssl_show_warn": True,
                "ca_certs": settings.OPENSEARCH_CA_CERTS,
            },
        )

    return OpenSearch(**client_kwargs)
