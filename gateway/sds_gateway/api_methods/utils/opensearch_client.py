from django.conf import settings
from opensearchpy import OpenSearch
from opensearchpy import RequestsHttpConnection
from requests.auth import HTTPBasicAuth


def get_opensearch_client():
    return OpenSearch(
        hosts=[{"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}],
        http_auth=HTTPBasicAuth(
            settings.OPENSEARCH_USER,
            settings.OPENSEARCH_INITIAL_ADMIN_PASSWORD,
        ),
        use_ssl=False,
        verify_certs=False,
        ssl_show_warn=False,
        connection_class=RequestsHttpConnection,
    )
