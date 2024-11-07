from rest_framework.test import APITestCase

from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client


class OpenSearchHealthCheckTest(APITestCase):
    def setUp(self):
        self.client = get_opensearch_client()

    def test_opensearch_health_check(self):
        assert self.client.ping()
