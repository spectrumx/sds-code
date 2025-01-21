from django.conf import settings
from opensearchpy import OpenSearch
from opensearchpy.connection.http_urllib3 import Urllib3HttpConnection


def get_opensearch_client():
    return OpenSearch(
        hosts=[{"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}],
        http_auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
        use_ssl=settings.OPENSEARCH_USE_SSL,
        verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
        ssl_assert_hostname=False,
        ssl_show_warn=False,
        connection_class=Urllib3HttpConnection,
        ca_certs=settings.OPENSEARCH_CA_CERTS,
    )
