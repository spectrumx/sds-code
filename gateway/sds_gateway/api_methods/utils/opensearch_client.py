from django.conf import settings
from opensearchpy import OpenSearch
from opensearchpy import RequestsHttpConnection
from requests.auth import HTTPBasicAuth


def get_opensearch_client():
    return OpenSearch(
        hosts=[{"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}],
        http_auth=HTTPBasicAuth(
            settings.OPENSEARCH_USER,
            settings.OPENSEARCH_PASSWORD,
        ),
        use_ssl=settings.OPENSEARCH_USE_SSL,
        verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
        ssl_show_warn=False,
        connection_class=RequestsHttpConnection,
        ca_certs=settings.OPENSEARCH_CA_CERTS,
    )
