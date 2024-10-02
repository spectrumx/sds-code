from django.conf import settings
from opensearchpy import OpenSearch


def get_opensearch_client():
    return OpenSearch(
        hosts=[{"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}],
        http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
        use_ssl=True,
        verify_certs=True,
        ssl_show_warn=False,
    )
