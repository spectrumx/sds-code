import logging
from pathlib import Path

from django.conf import settings

from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.utils.minio_client import get_minio_client
from sds_gateway.users.models import User

logger = logging.getLogger(__name__)


def reconstruct_tree(
    target_dir: Path,
    top_level_dir: Path,
    owner: User,
) -> tuple[Path, list[File]]:
    """Reconstructs a file tree from files in MinIO into a temp dir.

    Args:
        temp_dir:       The server location where the file tree will be reconstructed.
        top_level_dir:  The virtual directory of the tree root in SDS.
        owner:          The owner of the files to reconstruct.
    Returns:
        The path to the reconstructed file tree
        The list of File objects reconstructed
    """
    minio_client = get_minio_client()
    files_to_connect: list[File] = []
    target_dir = Path(target_dir)
    if not target_dir.is_absolute():
        msg = f"{target_dir=} must be an absolute path to reconstruct the file tree."
        raise ValueError(msg)
    if not target_dir.is_dir():
        msg = f"{target_dir=} must be a directory."
        raise ValueError(msg)
    reconstructed_root = target_dir / top_level_dir

    # Loop through File entries in the database
    for file_entry in File.objects.filter(
        directory__startswith=top_level_dir,
        owner=owner,
    ):
        files_to_connect.append(file_entry)
        local_file_path = Path(target_dir) / file_entry.directory / file_entry.name
        local_file_path.parent.mkdir(parents=True, exist_ok=True)
        minio_client.fget_object(
            settings.AWS_STORAGE_BUCKET_NAME,
            object_name=file_entry.file.name,
            file_path=str(local_file_path),
        )

    return reconstructed_root, files_to_connect


def find_rh_metadata_file(tmp_dir_path: Path) -> Path:
    """Finds the RadioHound metadata file in the given directory."""
    for file in tmp_dir_path.iterdir():
        # find file with .rh.json extension
        if file.name.endswith(".rh.json"):
            return file
    msg = "RadioHound metadata file not found"
    logger.exception(msg)
    raise FileNotFoundError(msg)
