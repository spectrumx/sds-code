import json
import uuid
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from loguru import logger as log

from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.utils.minio_client import get_minio_client
from sds_gateway.users.models import User


def is_metadata_file(file_name: str, capture_type: CaptureType) -> bool:
    if capture_type == CaptureType.RadioHound:
        return file_name.endswith(".rh.json")

    if capture_type == CaptureType.DigitalRF:
        # DigitalRF metadata files contain "properties" in the name
        # drf_properties.h5 and dmd_properties.h5 are metadata files
        return "properties" in file_name

    log.error(f"Invalid/unimplemented capture type: {capture_type}")
    msg = f"Invalid/unimplemented capture type: {capture_type}"
    raise ValueError(msg)


def reconstruct_tree(
    target_dir: Path,
    virtual_top_dir: Path,
    owner: User,
    drf_capture_type: CaptureType,
    rh_scan_group: uuid.UUID | None = None,
    *,
    verbose: bool = False,
) -> tuple[Path, list[File]]:
    """Reconstructs a file tree from files in MinIO into a temp dir.

    Args:
        target_dir:         The server dir where the file tree will be reconstructed
        virtual_top_dir:    The virtual directory of the tree root in SDS.
        owner:              The owner of the files to reconstruct.
        drf_capture_type:   The type of capture (DigitalRF or RadioHound)
        rh_scan_group:      Optional UUID to filter files by scan group.
        verbose:            Whether to log debug info.
    Returns:
        The path to the reconstructed file tree
        The list of File objects reconstructed
    """
    minio_client = get_minio_client()
    target_dir = Path(target_dir).resolve()
    virtual_top_dir = Path(virtual_top_dir).resolve()
    if not target_dir.is_absolute():
        msg = f"{target_dir=} must be an absolute path to reconstruct the file tree."
        raise ValueError(msg)
    if not target_dir.is_dir():
        msg = f"{target_dir=} must be a directory."
        raise ValueError(msg)

    reconstructed_root = Path(f"{target_dir}/{virtual_top_dir}").resolve()
    assert reconstructed_root.is_relative_to(
        target_dir,
    ), f"{reconstructed_root=} must be a subdirectory of {target_dir=}"

    owned_files_filter_by_capture_type = {
        CaptureType.DigitalRF: Q(
            owner=owner,
            directory__startswith=str(virtual_top_dir).rstrip("/"),  # parent dir match
        ),
        CaptureType.RadioHound: Q(
            owner=owner,
            name__endswith=".rh.json",
            directory__startswith=str(virtual_top_dir).rstrip("/"),  # parent dir match
        ),
    }
    # get all files owned by user in this directory
    user_file_queryset = File.objects.filter(
        owner=owner,
        is_deleted=False,
    )
    owned_files = {
        owned_file.name: owned_file
        for owned_file in user_file_queryset.filter(
            owned_files_filter_by_capture_type[drf_capture_type],
        )
    }
    if not owned_files:
        msg = f"No files found for {owner=} in {virtual_top_dir=}"
        log.warning(msg)
        return reconstructed_root, []

    # Reconstruct the tree
    if verbose:
        log.debug(f"Reconstructing tree with {len(owned_files)} files")
    for file_obj in owned_files.values():
        local_file_path = Path(
            f"{target_dir}/{file_obj.directory}/{file_obj.name}",
            # must be str concatenation to handle file_obj.directory being absolute
        ).resolve()
        assert local_file_path.is_relative_to(
            reconstructed_root,
        ), f"'{local_file_path=}' must be a subdirectory of '{reconstructed_root=}'"
        local_file_path.parent.mkdir(parents=True, exist_ok=True)
        if verbose:
            log.debug(f"Pulling {file_obj.file.name} as {local_file_path}")

        # If the file is a metadata file,
        # we need to download the file contents from MinIO
        # else, create a dummy file with the file name
        if is_metadata_file(file_obj.name, drf_capture_type):
            minio_client.fget_object(
                bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
                object_name=file_obj.file.name,
                file_path=str(local_file_path),
            )
        else:
            local_file_path.touch()

    # If scan_group provided, filter files by it
    if rh_scan_group and drf_capture_type == CaptureType.RadioHound:
        log.debug(f"Filtering RadioHound files by scan group {rh_scan_group}")
        files_to_connect = filter_rh_files_by_scan_group(
            owned_files=owned_files,
            scan_group=rh_scan_group,
            tmp_dir_path=reconstructed_root,
            verbose=verbose,
        )
    else:
        files_to_connect = list(owned_files.values())

    return reconstructed_root, files_to_connect


def filter_rh_files_by_scan_group(
    owned_files: dict[str, File],
    scan_group: uuid.UUID,
    tmp_dir_path: Path,
    extension: str = ".rh.json",
    *,
    verbose: bool = False,
) -> list[File]:
    """Filters RH files that belong to the given scan group.

    Args:
        owned_files:    Maps file names to File objects for metadata tracking
        scan_group:     UUID to search for in the file content
        tmp_dir_path:   Directory to search the file contents
        extension:      File extension to filter by
        verbose:        Whether to log debug info
    Returns:
        List of RH File's that belong to the scan group
    """
    matching_files: list[File] = []
    file_count = 0
    if verbose:
        log.debug(f"Listing files in {tmp_dir_path}")
        for path in tmp_dir_path.iterdir():
            log.debug(path)
    pattern = f"*{extension}"
    rh_glob = tmp_dir_path.rglob(pattern)
    for file_path in rh_glob:
        file_count += 1
        try:
            with file_path.open() as candidate_file:
                content = json.load(candidate_file)
            if (
                content.get("scan_group") == str(scan_group)
                and file_path.name in owned_files
            ):
                matching_files.append(owned_files[file_path.name])
            elif verbose:
                log.debug(f"Skipping {file_path.name} for scan group '{scan_group}'")
        except (json.JSONDecodeError, KeyError) as e:
            msg = f"Error processing {file_path}: {e}"
            log.warning(msg)
            continue

    if file_count == 0:
        msg = f"No files found in '{tmp_dir_path}' that match '{pattern}'"
        log.warning(msg)
    elif not matching_files:
        msg = f"No files found out of {file_count} files for scan group '{scan_group}'"
        log.warning(msg)

    return matching_files


def find_rh_metadata_file(tmp_dir_path: Path, extension: str = ".rh.json") -> Path:
    """Finds the RadioHound metadata file in the given directory."""
    for local_file in tmp_dir_path.iterdir():
        if local_file.name.endswith(extension):
            return local_file
    msg = "RadioHound metadata file not found"
    log.exception(msg)
    raise FileNotFoundError(msg)
