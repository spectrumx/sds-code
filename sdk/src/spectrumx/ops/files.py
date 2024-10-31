"""File operations for SpectrumX SDK."""

import mimetypes
import uuid
from datetime import datetime
from datetime import timedelta
from pathlib import Path

from spectrumx.models import File

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


def construct_file(file_path: Path, sds_dir: Path) -> File:
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
        directory=sds_dir,
        media_type=get_file_media_type(file_path),
        created_at=get_file_created_at(file_path),
        updated_at=get_file_updated_at(file_path),
        permissions=get_file_permissions(file_path),
    )


def generate_sample_file(uuid_to_set: uuid.UUID) -> File:
    """Generates a sample file for dry-run mode."""
    tz = datetime.now().astimezone().tzinfo
    created_at = datetime.now(tz=tz)
    updated_at = created_at
    expiration_date = datetime.now(tz=tz) + timedelta(days=30)

    sample_file = File(
        uuid=uuid_to_set,
        name="dry-run-file.txt",
        media_type="text/plain",
        size=888,
        directory=Path("./sds-files/dry-run/"),
        permissions="rw-rw-r--",
        created_at=created_at,
        updated_at=updated_at,
        expiration_date=expiration_date.date(),
        is_sample=True,
    )
    assert (
        sample_file.is_sample is True  # pyright: ignore[reportPrivateUsage]
    ), "SDS internal error: generated file is not a sample"
    return sample_file
