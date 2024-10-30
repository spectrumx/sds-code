from django.conf import settings
from minio import Minio


def get_minio_client():
    # Initialize MinIO client
    return Minio(
        settings.MINIO_ENDPOINT_URL,
        access_key=settings.AWS_ACCESS_KEY_ID,
        secret_key=settings.AWS_SECRET_ACCESS_KEY,
        secure=settings.MINIO_STORAGE_USE_HTTPS,
    )
