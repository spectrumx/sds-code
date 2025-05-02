"""API functions specific to files."""

# ruff: noqa: SLF001
# pyright: reportPrivateUsage=false

import os
import tempfile
import uuid
from enum import Enum
from enum import auto
from multiprocessing.synchronize import RLock
from pathlib import Path
from pathlib import PurePosixPath

from loguru import logger as log
from pydantic import UUID4

from spectrumx.client import Client
from spectrumx.errors import SDSError
from spectrumx.models.files import File
from spectrumx.ops import files
from spectrumx.ops.pagination import Paginator
from spectrumx.utils import log_user
from spectrumx.utils import log_user_warning

log.trace("Placeholder log to avoid reimporting or resolving unused import warnings.")


class FileUploadMode(Enum):
    """Modes for uploading files to SDS."""

    SKIP = auto()  # no upload or update needed
    UPDATE_METADATA_ONLY = auto()  # no file contents, update an existing file entry
    UPLOAD_CONTENTS_AND_METADATA = auto()  # create a new file uploading everything
    UPLOAD_METADATA_ONLY = auto()  # no file contents, create a new file entry
    # file contents are immutable, so there is no "UPDATE_CONTENTS_ONLY"


def get_file(client: Client, file_uuid: UUID4 | str) -> File:
    """Get a file instance by its ID. Only metadata is downloaded from SDS.

    Note this does not download the file contents from the server. File
        instances still need to have their contents downloaded to create
        a local copy - see `download_file()`.

    Args:
        file_uuid: The UUID of the file to retrieve.
    Returns:
        The file instance, or a sample file if in dry run mode.
    """

    uuid_to_set: UUID4 = (
        uuid.UUID(file_uuid) if isinstance(file_uuid, str) else file_uuid
    )

    if not client.dry_run:
        file_bytes = client._gateway.get_file_by_id(uuid=uuid_to_set.hex)
        return File.model_validate_json(file_bytes)

    log_user("Dry run enabled: a sample file is being returned instead")
    return files.generate_sample_file(uuid_to_set)


def download_file(
    *,
    client: Client,
    file_instance: File | None = None,
    file_uuid: UUID4 | str | None = None,
    to_local_path: Path | str | None = None,
    skip_contents: bool = False,
    warn_missing_path: bool = True,
) -> File:
    """Downloads a file from SDS: metadata and contents (unless skip_contents=True).

    Note this function always overwrites the local path of the file instance.
    """
    # prepare file instance
    if isinstance(file_instance, File):
        file_instance, valid_uuid, valid_local_path_or_none = (
            __extract_download_info_from_file_instance(
                file_instance=file_instance,
                to_local_path=to_local_path,
                warn_missing_path=warn_missing_path,
            )
        )
    # or fetch file info from SDS creating a new instance
    else:
        file_instance, valid_uuid, valid_local_path_or_none = (
            __pre_fetch_file_for_download(
                client=client,
                file_uuid=file_uuid,
                to_local_path=to_local_path,
                warn_missing_path=warn_missing_path,
            )
        )

    __download_file_contents_if_applicable(
        client=client,
        file_instance=file_instance,
        valid_uuid=valid_uuid,
        valid_local_path_or_none=valid_local_path_or_none,
        skip_contents=skip_contents,
    )
    return file_instance


def list_files(
    *,
    client: Client,
    sds_path: PurePosixPath | Path | str,
    verbose: bool = False,
) -> Paginator[File]:
    """Lists files in a given SDS path.

    Args:
        sds_path: The virtual directory on SDS to list files from.
    Returns:
        A paginator for the files in the given SDS path.
    """
    sds_path = PurePosixPath(sds_path)
    if client.dry_run:
        log_user("Dry run enabled: files will be simulated")
    pagination: Paginator[File] = Paginator(
        gateway=client._gateway,
        sds_path=sds_path,
        Entry=File,
        dry_run=client.dry_run,
        verbose=verbose,
    )

    return pagination


def upload_file(
    *,
    client: Client,
    local_file: File | Path | str,
    sds_path: PurePosixPath | Path | str = "/",
) -> File:
    """Uploads a file to SDS.

    If the file instance passed already has a directory set, `sds_path` will
    be prepended. E.g. given:
        `sds_path = 'baz'`; and
        `local_file.directory = 'foo/bar/'`, then:
    The file will be uploaded to `baz/foo/bar/` (under the user root in SDS) and
        the returned file instance will have its `directory` attribute updated
        to match this new path.

    Args:
        local_file:     The local file to upload.
        sds_path:       The virtual directory on SDS to upload the file to.
    Returns:
        The file instance with updated attributes, or a sample when in dry run.
    """
    # validate inputs
    if not isinstance(local_file, (File, Path, str)):
        msg = f"file_path must be a Path, str, or File instance, not {type(local_file)}"
        raise TypeError(msg)
    local_file = Path(local_file) if isinstance(local_file, str) else local_file
    sds_path = PurePosixPath(sds_path)

    # construct the file instance if needed
    if isinstance(local_file, File):
        file_instance = local_file.model_copy()
        if file_instance.directory:
            composed_sds_path = sds_path / file_instance.directory
            file_instance.directory = composed_sds_path
    else:
        file_instance = files.construct_file(local_file, sds_path=sds_path)
    del local_file

    return __upload_file_mux(client=client, file_instance=file_instance)


def delete_file(client: Client, file_uuid: UUID4 | str) -> bool:
    """Deletes a file from SDS by its UUID.

    Args:
        client: The client instance.
        file_uuid: The UUID of the file to delete.
    Returns:
        True if the file was deleted successfully,
        or if in dry run mode (simulating success).
    Raises:
        SDSError: If the file couldn't be deleted.
    """
    uuid_to_delete: UUID4 = (
        uuid.UUID(file_uuid) if isinstance(file_uuid, str) else file_uuid
    )

    if client.dry_run:
        log_user(f"Dry run enabled: would delete file with UUID {uuid_to_delete.hex}")
        return True

    return client._gateway.delete_file_by_id(uuid=uuid_to_delete.hex)


def __download_file_contents_if_applicable(
    client: Client,
    file_instance: File,
    *,
    valid_uuid: UUID4,
    valid_local_path_or_none: Path | None,
    skip_contents: bool = False,
) -> None:
    if skip_contents:
        msg = (
            "A file instance was provided and skip_contents "
            "is True: nothing to download."
        )
        log_user_warning(msg)
        return
    if client.dry_run:
        file_instance.local_path = valid_local_path_or_none
        log_user(
            "Dry run enabled: file contents would be "
            f"downloaded as {file_instance.local_path}"
        )
        return
    downloaded_path: Path = __download_file_contents(
        client=client,
        file_uuid=valid_uuid,
        target_path=valid_local_path_or_none,
        contents_lock=file_instance.contents_lock,  # pyright: ignore[reportPrivateUsage]
    )
    file_instance.local_path = downloaded_path


def __download_file_contents(
    *,
    client,
    file_uuid: UUID4 | str,
    contents_lock: RLock,
    target_path: Path | None = None,
) -> Path:
    """Downloads the contents of a file from SDS to a location on disk.

    If target_path is not provided, a temporary file is created.
    When provided, the parent of target_path will be created if it does not exist.

    Args:
        file_uuid:      The UUID of the file to download from SDS.
        target_path:    The local path to save the downloaded file to.
    Returns:
        The local path to the downloaded file.
    """
    if target_path is None:
        file_desc, file_name = tempfile.mkstemp()
        os.close(file_desc)
        target_path = Path(file_name)
    target_path = Path(target_path)
    uuid_to_set: UUID4 = (
        uuid.UUID(file_uuid) if isinstance(file_uuid, str) else file_uuid
    )
    if not client.dry_run:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open(mode="wb") as file_ptr, contents_lock:
            for chunk in client._gateway.get_file_contents_by_id(uuid=uuid_to_set.hex):
                file_ptr.write(chunk)
    else:
        log_user(f"Dry run enabled: file would be saved as {target_path}")
    return target_path


def __extract_download_info_from_file_instance(
    file_instance: File,
    *,
    to_local_path: Path | str | None,
    warn_missing_path: bool,
) -> tuple[File, UUID4, Path | None]:
    """Extracts from a file instance the info needed to download file contents."""
    if file_instance.uuid is None:
        msg = "The file passed is a local reference and cannot be downloaded."
        raise ValueError(msg)
    if to_local_path:
        file_instance.local_path = Path(to_local_path)
    if file_instance.local_path is None and warn_missing_path:
        msg = (
            "The file instance passed is missing a local path to "
            "download to. A temporary file will be created on disk."
        )
        log_user_warning(msg)
    valid_uuid = file_instance.uuid
    valid_local_path_or_none = file_instance.local_path
    return file_instance, valid_uuid, valid_local_path_or_none


def __get_upload_mode_and_asset(
    *, client: Client, file_instance: File
) -> tuple[FileUploadMode, uuid.UUID | None]:
    """Determines how to upload a file into SDS.

    Args:
        file_instance:  The file instance to get the upload mode for.
    Returns:
        The mode to upload the file in. Modes are:
            FileUploadMode.SKIP
            FileUploadMode.UPLOAD_CONTENTS_AND_METADATA
            FileUploadMode.UPLOAD_METADATA_ONLY
        Asset ID: The asset ID of the file in SDS, if it exists.

    SKIP is used when the file already exists in SDS and no changes are needed.
    UPLOAD_CONTENTS_AND_METADATA is used when the file is new or its contents
        have changed; it will create a new file entry with new contents.
    UPLOAD_METADATA_ONLY is used when the file contents are already in SDS, and
        it will create a new file entry while reusing existing contents from a
        sibling file.
    ---
    UPDATE_METADATA_ONLY is NOT returned here, as it might cause unintended changes.
        For this reason, "update" methods should be explicitly called by UUID.
    ---
    A "File" in SDS has immutable contents, so there is no "UPDATE_CONTENTS_ONLY".
    Note upload_* methods / modes create new assets in SDS, while update_* don't.
    """
    # always assume upload is needed in dry-run, since we can't contact the server
    if client.dry_run:
        return (
            FileUploadMode.UPLOAD_CONTENTS_AND_METADATA,
            None,
        )

    file_contents_check = client._gateway.check_file_contents_exist(
        file_instance=file_instance
    )
    asset_id = file_contents_check.asset_id

    if file_contents_check.file_exists_in_tree:
        return FileUploadMode.SKIP, asset_id
    if file_contents_check.file_contents_exist_for_user:
        return FileUploadMode.UPLOAD_METADATA_ONLY, asset_id
    return FileUploadMode.UPLOAD_CONTENTS_AND_METADATA, asset_id


def __pre_fetch_file_for_download(
    client: Client,
    file_uuid: UUID4 | str | None,
    to_local_path: Path | str | None,
    *,
    warn_missing_path: bool,
) -> tuple[File, UUID4, Path | None]:
    """Pre-fetches file metadata from SDS to get info for downloading contents."""
    if file_uuid is None:
        msg = "Expected a file instance or UUID to download."
        raise ValueError(msg)
    if to_local_path is None and warn_missing_path:
        msg = "The file will be downloaded as temporary."
        log_user_warning(msg)

    valid_local_path_or_none: Path | None = (
        Path(to_local_path) if to_local_path else None
    )

    valid_uuid: UUID4 = (
        uuid.UUID(file_uuid) if isinstance(file_uuid, str) else file_uuid
    )
    if client.dry_run:
        log_user("Dry run enabled: a sample file is being returned instead")
        file_instance: File = files.generate_sample_file(valid_uuid)
    else:
        file_bytes: bytes = client._gateway.get_file_by_id(uuid=valid_uuid.hex)
        file_instance: File = File.model_validate_json(file_bytes)
    return file_instance, valid_uuid, valid_local_path_or_none


def __upload_file_mux(*, client: Client, file_instance: File) -> File:  # noqa: C901
    """Uploads a file instance to SDS, choosing the right upload mode."""
    file_path = file_instance.local_path
    # check whether sds already has this file for this user
    upload_mode, asset_id = __get_upload_mode_and_asset(
        client=client, file_instance=file_instance
    )
    verbose = client.verbose

    if client.dry_run:
        log_user(f"Dry run enabled: skipping upload of '{file_path}'")
        return file_instance

    match upload_mode:
        case FileUploadMode.SKIP:
            if verbose:
                log_user(f"Skipping upload of existing '{file_path}'")
            return file_instance
        case FileUploadMode.UPLOAD_CONTENTS_AND_METADATA:
            if verbose:
                log_user(f"Uploading contents and metadata for '{file_path}'")
            return __upload_contents_and_metadata(
                client=client, file_instance=file_instance
            )
        case FileUploadMode.UPLOAD_METADATA_ONLY:
            if verbose:
                log_user(f"Uploading only metadata for '{file_path}'")
                log.debug(
                    f"Uploading only metadata '{file_path}' with sibling '{asset_id}'"
                )
            if asset_id is None:
                msg = "Expected an asset ID when uploading metadata only"
                raise SDSError(msg)
            return __upload_new_file_metadata_only(
                client=client, file_instance=file_instance, sibling_uuid=asset_id
            )
        case FileUploadMode.UPDATE_METADATA_ONLY:  # pragma: no cover
            if verbose:
                log_user(f"Updating metadata for '{file_path}'")
                log.debug(f"Updating metadata '{file_path}' with asset '{asset_id}'")
            assert asset_id is not None, "Expected an asset ID when updating metadata"
            return __update_existing_file_metadata_only(
                client=client, file_instance=file_instance, asset_id=asset_id
            )
        case _:  # pragma: no cover
            msg = f"Unexpected upload mode: {upload_mode}"
            raise SDSError(msg)


def __upload_contents_and_metadata(
    *,
    client: Client,
    file_instance: File,
) -> File:
    """UPLOADS a new file instance to SDS with contents and metadata.

    Args:
        client:         The SDS client instance.
        file_instance:  The file instance to upload.
    Returns:
        The file instance with updated attributes.
    """
    if client.dry_run:
        log_user("Dry run enabled: would upload contents and metadata")
        return file_instance

    assert not client.dry_run, "Internal error: expected dry run to be disabled."
    file_response = client._gateway.upload_new_file(file_instance=file_instance)
    uploaded_file = File.model_validate_json(file_response)
    uploaded_file.local_path = file_instance.local_path
    return uploaded_file


def __update_existing_file_metadata_only(
    *, client: Client, file_instance: File, asset_id: UUID4 | None
) -> File:
    """UPDATES an existing file instance with new metadata.

    ---
        Note: favor use of the safer `__upload_new_file_metadata_only()`,
        which creates a new File entry reusing the contents of a sibling file.
    ---

    Useful when the files is already instantiated in SDS and the file
        contents did not change: only the metadata needs to be updated.

    Args:
        file_instance:  The file instance with new metadata to update.
    Returns:
        The file instance with updated attributes.
    """
    if asset_id is not None:
        file_instance.uuid = asset_id

    if client.dry_run:
        msg = (
            "Dry run enabled: would update metadata "
            f"only for file '{file_instance.uuid}'"
        )
        log_user(msg)
        return file_instance

    assert not client.dry_run, "Internal error: expected dry run to be disabled."
    file_response = client._gateway.update_existing_file_metadata(
        file_instance=file_instance
    )
    updated_file = File.model_validate_json(file_response)
    updated_file.local_path = file_instance.local_path
    return updated_file


def __upload_new_file_metadata_only(
    *, client: Client, file_instance: File, sibling_uuid: UUID4
) -> File:
    """UPLOADS a new file instance to SDS, skipping the file contents.

    Useful when there are identical files in different locations: only their
        metadata needs to be uploaded to SDS. There must be a sibling file
        with the right contents, under the same user, already in SDS for this
        method to succeed.

    The sibling entry is not modified and doesn't need to exist locally.

    Args:
        file_instance:  The file instance with new metadata.
        sibling_uuid:   The UUID of the file which contents are identical to.
    Returns:
        The file instance with updated attributes.
    """
    if client.dry_run:
        log_user("Dry run enabled: uploading metadata only")
        return file_instance

    assert not client.dry_run, "Internal error: expected dry run to be disabled."
    file_response = client._gateway.upload_new_file_metadata_only(
        file_instance=file_instance, sibling_uuid=sibling_uuid
    )
    uploaded_file = File.model_validate_json(file_response)
    uploaded_file.local_path = file_instance.local_path
    return uploaded_file
