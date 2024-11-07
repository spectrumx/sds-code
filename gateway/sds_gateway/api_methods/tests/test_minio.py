from django.conf import settings
from minio.error import MinioException
from rest_framework.test import APITestCase

from sds_gateway.api_methods.utils.minio_client import get_minio_client


def try_get_bucket(client):
    try:
        return client.bucket_exists(settings.AWS_STORAGE_BUCKET_NAME)
    except (MinioException, ConnectionError) as e:
        return str(e)


class MinioHealthCheckTest(APITestCase):
    def setUp(self):
        self.client = get_minio_client()

    def test_minio_health_check(self):
        response = try_get_bucket(self.client)

        assert response is True
