from loguru import logger as log
from opensearchpy import OpenSearch
from opensearchpy import RequestsHttpConnection
from requests.auth import HTTPBasicAuth


def build_opensearch_client(
    *,
    host: str,
    port: int,
    user: str = "",
    password: str = "",
    use_ssl: bool = False,
    verify_certs: bool = False,
    ca_certs: str | None = None,
) -> OpenSearch:
    payload = {
        "hosts": [{"host": host, "port": port}],
        "use_ssl": use_ssl,
        "verify_certs": verify_certs,
        "ssl_show_warn": False,
        "connection_class": RequestsHttpConnection,
    }
    if user:
        payload["http_auth"] = HTTPBasicAuth(user, password)
    if verify_certs:
        if not ca_certs:
            msg = (
                "OPENSEARCH_VERIFY_CERTS is True but OPENSEARCH_CA_CERTS is not set. "
                "Provide a CA bundle path or set OPENSEARCH_VERIFY_CERTS to False."
            )
            raise ValueError(msg)
        log.info("OPENSEARCH_VERIFY_CERTS is True. Verifying certificates.")
        payload["ca_certs"] = ca_certs
    return OpenSearch(**payload)
