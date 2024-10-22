import shutil
from pathlib import Path

from django.conf import settings

from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.utils.minio_client import get_minio_client


def reconstruct_tree(temp_dir, top_level_dir):
    minio_client = get_minio_client()
    files_to_connect = []
    tmp_dir_path = str(Path(temp_dir) / top_level_dir)

    # Loop through File entries in the database
    for file_entry in File.objects.filter(directory__icontains=top_level_dir):
        # Add the file to the list of files to connect
        files_to_connect.append(file_entry.uuid)

        # Construct the local file path
        local_file_path = Path(temp_dir) / file_entry.directory / file_entry.name

        # Ensure the directory exists
        local_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Download the file from MinIO
        minio_client.fget_object(
            settings.AWS_STORAGE_BUCKET_NAME,
            file_entry.file.name,
            str(local_file_path),
        )

    return tmp_dir_path, files_to_connect


def destroy_tree(temp_dir):
    # Remove the directory and its contents
    shutil.rmtree(temp_dir)
