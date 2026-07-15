from django.conf import settings

from common.sds_opensearch_query.client import build_opensearch_client


def get_opensearch_client():
    return build_opensearch_client(
        host=settings.OPENSEARCH_HOST,
        port=settings.OPENSEARCH_PORT,
        user=settings.OPENSEARCH_USER,
        password=settings.OPENSEARCH_PASSWORD,
        use_ssl=settings.OPENSEARCH_USE_SSL,
        verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
        ca_certs=settings.OPENSEARCH_CA_CERTS,
    )
