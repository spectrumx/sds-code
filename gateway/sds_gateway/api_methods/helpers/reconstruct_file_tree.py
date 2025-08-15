import json
import uuid
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.db.models import QuerySet
from loguru import logger as log

from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.utils.minio_client import get_minio_client
from sds_gateway.users.models import User

RH_DEFAULT_EXTENSION = ".rh.json"


def _is_metadata_file(file_name: str, capture_type: CaptureType) -> bool:
    if capture_type == CaptureType.RadioHound:
        return file_name.endswith(RH_DEFAULT_EXTENSION)

    if capture_type == CaptureType.DigitalRF:
        # DigitalRF metadata files contain "properties" in the name
        # drf_properties.h5 and dmd_properties.h5 are metadata files
        return "properties" in file_name

    log.error(f"Invalid/unimplemented capture type: {capture_type}")
    msg = f"Invalid/unimplemented capture type: {capture_type}"
    raise ValueError(msg)


def _get_drf_sample_file_name_bounds(
    file_queryset: QuerySet[File],
) -> tuple[str, str] | tuple[None, None]:
    """Get the timestamp of the first file in the given directory."""
    # get the rf data file names
    # all rf data files start with rf@ per the notes here:
    # https://github.com/MITHaystack/digital_rf/blob/master/python/digital_rf/digital_rf_hdf5.py#L793
    drf_file_objs = file_queryset.filter(
        name__startswith="rf@",
    )

    # sort the rf data file objs
    # use the same sorting as in ilsdrf():
    # https://github.com/MITHaystack/digital_rf/blob/ca7d715f27d527a11125dbd4c5971627c30efe31/python/digital_rf/list_drf.py#L253
    # should return the lowest timestamp first
    drf_file_objs = drf_file_objs.order_by("name")

    if not drf_file_objs.exists():
        msg = "No RF sample data files found"
        log.error(msg)
        return None, None

    # get the first and last rf data file names
    first_drf_data_file_name = drf_file_objs.first().name  # pyright: ignore[reportOptionalMemberAccess]
    last_drf_data_file_name = drf_file_objs.last().name  # pyright: ignore[reportOptionalMemberAccess]

    return first_drf_data_file_name, last_drf_data_file_name


def _get_dmd_first_sample_file_name(file_queryset: QuerySet[File]) -> str | None:
    """Get the first sample file name for a DigitalRF capture."""
    # follows the process for getting the bounds from
    # DigitalMetadataReader read_flatdict() function
    # https://github.com/MITHaystack/digital_rf/blob/ca7d715f27d527a11125dbd4c5971627c30efe31/python/digital_rf/digital_metadata.py#L627
    dmd_file_objs = file_queryset.filter(
        name__startswith="metadata@",
    )

    # sort the dmd file objs
    dmd_file_objs = dmd_file_objs.order_by("name")

    if not dmd_file_objs.exists():
        msg = "No metadata sample files found"
        log.error(msg)
        return None

    # get the first dmd file name
    return dmd_file_objs.first().name  # pyright: ignore[reportOptionalMemberAccess]


def _get_list_of_capture_files(
    capture_type: CaptureType,
    virtual_top_dir: Path,
    owner: User,
    drf_channel: str | None = None,
    rh_scan_group: uuid.UUID | None = None,
    target_dir: Path | None = None,
    *,
    verbose: bool = False,
) -> QuerySet[File]:
    """Returns the queryset of files to fetch from MinIO."""
    # Normalize the virtual_top_dir to ensure consistent matching
    normalized_virtual_top_dir = str(virtual_top_dir).rstrip("/")

    owned_files_filter_by_capture_type = {
        # matches .h5, .hdf, .hdf5, .he5 (case-insensitive)
        CaptureType.DigitalRF: Q(
            owner=owner,
            name__iregex=r"\.(hdf5?|he?5)$",
        )
        & (
            Q(directory=normalized_virtual_top_dir)
            | Q(directory__startswith=f"{normalized_virtual_top_dir}/")
        ),
        CaptureType.RadioHound: Q(
            owner=owner,
            name__endswith=RH_DEFAULT_EXTENSION,
        )
        & (
            Q(directory=normalized_virtual_top_dir)
            | Q(directory__startswith=f"{normalized_virtual_top_dir}/")
        ),
    }

    # get all files owned by user in this directory
    user_file_queryset = File.objects.filter(
        owner=owner,
        is_deleted=False,
    ).filter(
        owned_files_filter_by_capture_type[capture_type],
    )

    # TODO: filter files by depth to avoid fetching too many files

    if verbose:
        log.debug(
            f"Found {len(user_file_queryset)} files for {owner} in "
            f"{virtual_top_dir} for {capture_type} type",
        )
    if not user_file_queryset.exists():
        return user_file_queryset.none()

    match capture_type:
        case CaptureType.DigitalRF:
            assert drf_channel, "drf_channel must be provided for DigitalRF captures"
            # filter files where the channel name appears as a directory component
            filtered_files = user_file_queryset.filter(
                directory__regex=rf".*/{drf_channel}(/.*)?$",
            )
        case _:
            filtered_files = user_file_queryset

    if verbose:
        log.debug(f"Filtered {len(filtered_files)} files")

    return filtered_files


def _get_filenames_of_interest_for_capture(
    capture_type: CaptureType,
    file_queryset: QuerySet[File],
    *,
    verbose: bool = False,
) -> set[str]:
    """Get the set of filenames that are of interest for reconstruction."""
    # TODO: consider changing this to return a queryset instead of a set of file names
    filenames_of_interest = set()

    # if capture type is digital rf, get the first and last rf data file names
    match capture_type:
        case CaptureType.DigitalRF:
            first_drf_data_file_name, last_drf_data_file_name = (
                _get_drf_sample_file_name_bounds(file_queryset)
            )
            first_dmd_data_file_name = _get_dmd_first_sample_file_name(file_queryset)

            fatal_msg = ""
            if first_drf_data_file_name:
                filenames_of_interest.add(first_drf_data_file_name)
            else:
                fatal_msg += "No RF data start file found (e.g. matching 'rf@*.h5').\n"
            if last_drf_data_file_name:
                filenames_of_interest.add(last_drf_data_file_name)
            else:
                fatal_msg += "No RF data end file found (e.g. matching 'rf@*.h5').\n"

            # metadata@ files are optional
            if first_dmd_data_file_name:
                filenames_of_interest.add(first_dmd_data_file_name)

            if fatal_msg:
                fatal_msg = (
                    "Some files that are required to get sample bounds for DRF captures"
                    f"are missing:\n{fatal_msg.strip()}\nMetadata extraction will fail "
                    "without these file contents loaded correctly."
                )
                log.warning(fatal_msg)
                raise ValueError(fatal_msg)

    if verbose:
        log.debug(
            f"Got {len(filenames_of_interest)} filenames of interest ({capture_type})",
        )

    return filenames_of_interest


def _check_fetch_conditions(
    file_name: str,
    capture_type: CaptureType,
    filenames_of_interest: set[str],
) -> bool:
    """
    Check if the contents of the given files of interest should be fetched from MinIO.

    This exists because not all files of interest will have their contents fetched. For
    example, metadata files are interesting for indexing and lightweight, but raw data
    files may make up most of storage, but are not needed for indexing.

    Args:
        file_name:              The name of the file to check
        capture_type:           The type of capture
        filenames_of_interest:  The set of file names that are of interest
    Returns:
        True if the file contents should be fetched, False otherwise
    """

    match (
        file_name,
        _is_metadata_file(file_name=file_name, capture_type=capture_type),
    ):
        case (name, _) if name in filenames_of_interest:
            return True
        case (_, True):
            return True
        case _:
            return False


def reconstruct_tree(
    target_dir: Path,
    virtual_top_dir: Path,
    owner: User,
    capture_type: CaptureType,
    drf_channel: str | None = None,
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

    capture_files = _get_list_of_capture_files(
        capture_type=capture_type,
        virtual_top_dir=virtual_top_dir,
        owner=owner,
        drf_channel=drf_channel,
        rh_scan_group=rh_scan_group,
        target_dir=target_dir,
        verbose=verbose,
    )

    reconstructed_root = Path(f"{target_dir}/{virtual_top_dir}").resolve()
    assert reconstructed_root.is_relative_to(
        target_dir,
    ), f"{reconstructed_root=} must be a subdirectory of {target_dir=}"

    if not capture_files:
        msg = f"No files found for {owner=} in {virtual_top_dir=}"
        log.warning(msg)
        return reconstructed_root, []

    if verbose:
        log.debug(f"Reconstructing tree with {len(capture_files)} files")

    filenames_of_interest = _get_filenames_of_interest_for_capture(
        capture_type=capture_type,
        file_queryset=capture_files,
        verbose=verbose,
    )

    # reconstruct the tree
    for file_obj in capture_files:
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
        fetch_file_contents = _check_fetch_conditions(
            file_name=file_obj.name,
            capture_type=capture_type,
            filenames_of_interest=filenames_of_interest,
        )
        if fetch_file_contents:
            minio_client.fget_object(
                bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
                object_name=file_obj.file.name,
                file_path=str(local_file_path),
            )
        else:
            local_file_path.touch()

    # filter out rh files of different scan groups
    # this needs to happen after the contents are fetched, unfortunately, because the
    # scan group information is part of the file contents.
    files_to_connect = _filter_files_after_fetching(
        drf_capture_type=capture_type,
        rh_scan_group=rh_scan_group,
        reconstructed_root=reconstructed_root,
        owned_files=capture_files,
        verbose=verbose,
    )

    return reconstructed_root, files_to_connect


def _filter_files_after_fetching(
    drf_capture_type: CaptureType,
    rh_scan_group: uuid.UUID | None,
    reconstructed_root: Path,
    owned_files: QuerySet[File],
    *,
    verbose: bool,
) -> list[File]:
    # only connect RH files of the same scan group
    if rh_scan_group and drf_capture_type == CaptureType.RadioHound:
        log.debug(f"Filtering RadioHound files by scan group {rh_scan_group}")
        files_to_connect = filter_rh_files_by_scan_group(
            rh_capture_files=owned_files,
            scan_group=rh_scan_group,
            tmp_dir_path=reconstructed_root,
            verbose=verbose,
        )
    else:
        files_to_connect = list(owned_files)
    return files_to_connect


def filter_rh_files_by_scan_group(
    rh_capture_files: QuerySet[File],
    scan_group: uuid.UUID,
    tmp_dir_path: Path,
    extension: str = RH_DEFAULT_EXTENSION,
    *,
    verbose: bool = False,
) -> list[File]:
    """Filters RH files that belong to the given scan group.

    Args:
        rh_capture_files:   QuerySet of owned RH files to filter
        scan_group:         UUID to search for in the file content
        tmp_dir_path:       Directory to search the file contents
        extension:          File extension to filter by
        verbose:            Whether to log debug info
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
    owned_files_map = {owned_file.name: owned_file for owned_file in rh_capture_files}
    for file_path in rh_glob:
        file_count += 1
        try:
            with file_path.open() as candidate_file:
                content = json.load(candidate_file)
            if (
                content.get("scan_group") == str(scan_group)
                and file_path.name in owned_files_map
            ):
                matching_files.append(owned_files_map[file_path.name])
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
    elif verbose:
        log.debug(
            f"Found {len(matching_files)} / {file_count} for scan group '{scan_group}'",
        )

    return matching_files


def find_rh_metadata_file(
    tmp_dir_path: Path,
    extension: str = RH_DEFAULT_EXTENSION,
) -> Path:
    """Finds the RadioHound metadata file in the given directory."""
    for local_file in tmp_dir_path.iterdir():
        if local_file.name.endswith(extension):
            return local_file
    msg = "RadioHound metadata file not found"
    log.exception(msg)
    raise FileNotFoundError(msg)
