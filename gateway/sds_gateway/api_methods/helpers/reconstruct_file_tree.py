import json
import logging
import uuid
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
    scan_group: uuid.UUID | None = None,
) -> tuple[Path, list[File]]:
    """Reconstructs a file tree from files in MinIO into a temp dir.

    Args:
        target_dir: The server location where the file tree will be reconstructed.
        top_level_dir: The virtual directory of the tree root in SDS.
        owner: The owner of the files to reconstruct.
        scan_group: Optional UUID to filter files by scan group.
    Returns:
        The path to the reconstructed file tree
        The list of File objects reconstructed
    """
    minio_client = get_minio_client()
    target_dir = Path(target_dir)
    if not target_dir.is_absolute():
        msg = f"{target_dir=} must be an absolute path to reconstruct the file tree."
        raise ValueError(msg)
    if not target_dir.is_dir():
        msg = f"{target_dir=} must be a directory."
        raise ValueError(msg)
    reconstructed_root = target_dir / top_level_dir

    # Get all files owned by user in this directory
    owned_files = {
        f.name: f
        for f in File.objects.filter(
            directory__startswith=top_level_dir,
            owner=owner,
        )
    }

    # Reconstruct the tree
    for file_obj in owned_files.values():
        local_file_path = Path(target_dir) / file_obj.directory / file_obj.name
        local_file_path.parent.mkdir(parents=True, exist_ok=True)
        minio_client.fget_object(
            settings.AWS_STORAGE_BUCKET_NAME,
            object_name=file_obj.file.name,
            file_path=str(local_file_path),
        )

    # If scan_group provided, filter files by it
    if scan_group:
        files_to_connect = find_files_in_scan_group(
            scan_group,
            reconstructed_root,
            owned_files,
        )
    else:
        files_to_connect = list(owned_files.values())

    return reconstructed_root, files_to_connect


def find_files_in_scan_group(
    scan_group: uuid.UUID,
    tmp_dir_path: Path,
    owned_files: dict[str, File],
) -> list[File]:
    """Finds all files in directory with scan_group in the file content.

    Args:
        scan_group: UUID to search for in the file content
        tmp_dir_path: Directory to search in

    Returns:
        List of File objects that contain the scan_group in their metadata
    """
    matching_files: list[File] = []
    for file_path in tmp_dir_path.rglob("*.rh.json"):
        try:
            with file_path.open() as f:
                content = json.load(f)
                if (
                    content.get("scan_group") == str(scan_group)
                    and file_path.name in owned_files
                ):
                    matching_files.append(owned_files[file_path.name])
        except (json.JSONDecodeError, KeyError) as e:
            msg = f"Error processing {file_path}: {e}"
            logger.warning(msg)
            continue

    return matching_files


def find_rh_metadata_file(tmp_dir_path: Path) -> Path:
    """Finds the RadioHound metadata file in the given directory."""
    for file in tmp_dir_path.iterdir():
        # find file with .rh.json extension
        if file.name.endswith(".rh.json"):
            return file
    msg = "RadioHound metadata file not found"
    logger.exception(msg)
    raise FileNotFoundError(msg)
