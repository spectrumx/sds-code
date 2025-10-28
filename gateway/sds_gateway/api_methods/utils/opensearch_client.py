from django.conf import settings
from loguru import logger as log
from opensearchpy import OpenSearch
from opensearchpy import RequestsHttpConnection
from requests.auth import HTTPBasicAuth


def get_opensearch_client():
    payload = {
        "hosts": [{"host": settings.OPENSEARCH_HOST, "port": settings.OPENSEARCH_PORT}],
        "http_auth": HTTPBasicAuth(
            settings.OPENSEARCH_USER,
            settings.OPENSEARCH_PASSWORD,
        ),
        "use_ssl": settings.OPENSEARCH_USE_SSL,
        "verify_certs": settings.OPENSEARCH_VERIFY_CERTS,
        "ssl_show_warn": False,
        "connection_class": RequestsHttpConnection,
    }
    if settings.OPENSEARCH_VERIFY_CERTS:
        if not settings.OPENSEARCH_CA_CERTS:
            msg = (
                "OPENSEARCH_VERIFY_CERTS is True but OPENSEARCH_CA_CERTS is not set."
                "Not using SSL."
            )
            log.warning(msg)
        else:
            log.info("OPENSEARCH_VERIFY_CERTS is True. Verifying certificates.")
            payload["ca_certs"] = settings.OPENSEARCH_CA_CERTS
    return OpenSearch(**payload)
