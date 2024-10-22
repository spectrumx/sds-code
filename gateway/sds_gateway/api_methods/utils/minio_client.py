from django.conf import settings
from minio import Minio


def get_minio_client():
    # Initialize MinIO client
    return Minio(
        settings.MINIO_ENDPOINT_URL,  # Replace with your MinIO server URL
        access_key=settings.AWS_ACCESS_KEY_ID,  # Replace with your access key
        secret_key=settings.AWS_SECRET_ACCESS_KEY,  # Replace with your secret key
        secure=settings.MINIO_STORAGE_USE_HTTPS,  # Set to True if using HTTPS
    )
