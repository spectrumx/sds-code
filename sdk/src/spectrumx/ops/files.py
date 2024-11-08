"""File operations for SpectrumX SDK."""

import mimetypes
import uuid
from collections.abc import Generator
from datetime import datetime
from datetime import timedelta
from pathlib import Path

from spectrumx.models import File
from spectrumx.utils import log_user

_tz = datetime.now().astimezone().tzinfo


def get_file_media_type(file_path: Path) -> str:
    """Returns the media type of a file.

    Args:
        file_path: The path to the file.

    https://www.iana.org/assignments/media-types/media-types.xhtml#application
    https://developer.mozilla.org/en-US/docs/Web/HTTP/MIME_types
    """
    mime_type, _encoding = mimetypes.guess_type(file_path)
    return mime_type or "application/octet-stream"


def get_file_permissions(file_path: Path) -> str:
    """Returns the permissions of a file."""
    permissions = file_path.stat().st_mode
    binary_rep = f"{permissions:09b}"[-9:]
    permission_map = ["r", "w", "x"]
    return "".join(
        permission_map[i % 3] if binary_rep[i] == "1" else "-" for i in range(9)
    )


def get_file_created_at(file_path: Path) -> datetime:
    """Returns the creation timestamp of a file."""
    return datetime.fromtimestamp(file_path.stat().st_ctime, tz=_tz)


def get_file_updated_at(file_path: Path) -> datetime:
    """Returns the last update timestamp of a file."""
    return datetime.fromtimestamp(file_path.stat().st_mtime, tz=_tz)


def construct_file(file_path: Path, sds_path: Path) -> File:
    """Constructs a file instance from a local file."""
    file_path = Path(file_path)
    if not file_path.exists():
        msg = f"File not found: {file_path}"
        raise FileNotFoundError(msg)
    return File(
        name=file_path.name,
        expiration_date=None,
        local_path=file_path,
        size=file_path.stat().st_size,
        directory=sds_path,
        media_type=get_file_media_type(file_path),
        created_at=get_file_created_at(file_path),
        updated_at=get_file_updated_at(file_path),
        permissions=get_file_permissions(file_path),
    )


def is_valid_file(file_path: Path) -> tuple[bool, list[str]]:
    """Returns True if the path is a valid file.
    A similar check is also performed at the server side.

    Returns:
        True/False whether the file is valid.
        Reasons for invalidity otherwise.
    """
    file_mime = get_file_media_type(file_path)
    disallowed_mimes = [
        "application/octet-stream",  # generic binary
        "application/x-msdownload",  # .exe
        "application/x-msdos-program",  # .com
        "application/x-msi",  # .msi
    ]
    is_valid_mime = file_mime not in disallowed_mimes
    reasons: list[str] = []
    if not is_valid_mime:
        reasons.append(f"Invalid MIME type: {file_mime}")
    if not file_path.is_file():
        reasons.append("Not a file")
    if file_path.stat().st_size == 0:
        reasons.append("Empty file")
    final_decision = (
        file_path.is_file() and file_path.stat().st_size > 0 and is_valid_mime
    )
    return final_decision, reasons


def get_valid_files(
    local_path: Path, *, warn_skipped: bool = False
) -> Generator[File, None, None]:
    """Yields valid SDS files in the given directory.

    Args:
        local_path: The path to the directory.
    Yields:
        File instances.
    """
    recursive_file_list = local_path.rglob("*")
    for file_path in recursive_file_list:
        if not file_path.is_file():
            continue
        is_valid, reasons = is_valid_file(file_path)
        if not is_valid:
            if warn_skipped:
                log_user(f"Skipping {file_path}: {', '.join(reasons)}")
            continue
        try:
            yield construct_file(file_path, local_path)
        except FileNotFoundError:
            continue


def generate_sample_file(uuid_to_set: uuid.UUID) -> File:
    """Generates a sample file for dry-run mode."""
    tz = datetime.now().astimezone().tzinfo
    created_at = datetime.now(tz=tz)
    updated_at = created_at
    expiration_date = datetime.now(tz=tz) + timedelta(days=30)
    trailing_uuid_hex = uuid_to_set.hex[-6:]

    sample_file = File(
        uuid=uuid_to_set,
        name=f"dry-run-{trailing_uuid_hex}.txt",
        media_type="text/plain",
        size=888,
        directory=Path("./sds-files/dry-run/"),
        permissions="rw-rw-r--",
        created_at=created_at,
        updated_at=updated_at,
        expiration_date=expiration_date,
        is_sample=True,  # always True for sample files
    )
    assert (
        sample_file.is_sample is True  # pyright: ignore[reportPrivateUsage]
    ), "SDS internal error: generated file is not a sample"
    return sample_file
