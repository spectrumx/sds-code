"""File operations for SpectrumX SDK."""

import mimetypes
import uuid
from collections.abc import Generator
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from pathlib import PurePosixPath

from loguru import logger as log

from spectrumx.models.files import File
from spectrumx.utils import log_user
from spectrumx.utils import log_user_warning

_tz = datetime.now().astimezone().tzinfo


def _load_undesired_globs(ignore_file: Path | None = None) -> list[str]:
    """Returns a list of undesired glob patterns loaded from a .sds-ignore file.

    The .sds-ignore file is similar to a .gitignore, with one pattern per line.
    Comments are marked with a # and ignored on read.
    Simple wildcards are supported, but recursive ones (**) are not.
    Exclusions with a ! prefix are not supported.
    """
    undesired_basenames = []
    if ignore_file is None:
        ignore_file = Path(__file__).parent / ".sds-ignore"
    comment_indicator = "#"
    if ignore_file.is_file():
        with ignore_file.open("r") as f:
            undesired_basenames = [
                line.split(comment_indicator, maxsplit=1)[0].strip()
                for line in f.read().splitlines()
                if not line.lstrip().startswith(comment_indicator)
            ]
            undesired_basenames = sorted([line for line in undesired_basenames if line])
    else:
        log.info("No .sds-ignore file found")
    return undesired_basenames


DISALLOWED_GLOBS = _load_undesired_globs()


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


def construct_file(file_path: Path, sds_path: Path | PurePosixPath) -> File:
    """Constructs a file instance from a local file. File has to exist on disk."""
    file_path = Path(file_path)
    if not file_path.exists():
        msg = f"File not found: {file_path}"
        raise FileNotFoundError(msg)
    return File(
        name=file_path.name,
        expiration_date=None,
        local_path=file_path,
        size=file_path.stat().st_size,
        directory=PurePosixPath(sds_path),
        media_type=get_file_media_type(file_path),
        created_at=get_file_created_at(file_path),
        updated_at=get_file_updated_at(file_path),
        permissions=get_file_permissions(file_path),
    )


def is_valid_file(
    file_path: Path, *, check_sds_ignore: bool = True
) -> tuple[bool, list[str]]:
    """Returns True if the path is a valid file.
    A similar check is also performed at the server side.

    About check_sds_ignore's glob matches, we use Pathlib.match();
        see their docs to know more about what's supported:
        https://docs.python.org/3/library/pathlib.html#pathlib.PurePath.match

    Args:
        file_path:          The path to the file.
        check_sds_ignore:   Whether to check for undesired glob patterns.
    Returns:
        True/False whether the file is valid.
        Reasons for invalidity otherwise.
    """
    file_mime = get_file_media_type(file_path)
    disallowed_mimes = [
        "application/x-msdownload",  # .exe
        "application/x-msdos-program",  # .com
        "application/x-msi",  # .msi
    ]
    is_valid_mime = file_mime not in disallowed_mimes
    reasons: list[str] = []
    if check_sds_ignore and any(file_path.match(glob) for glob in DISALLOWED_GLOBS):
        reasons.append(
            f"Path matched one or more undesired glob patterns for '{file_path.name}'"
        )
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


def get_valid_files(local_path: Path, *, warn_skipped: bool = False) -> Generator[File]:
    """Yields valid SDS files in the given directory.

    Args:
        local_path: The path to the directory.
    Yields:
        File instances.
    """
    recursive_file_list = local_path.rglob("*")
    successful_files: int = 0
    ignored_files: int = 0
    for file_path in recursive_file_list:
        if not file_path.is_file():
            continue
        is_valid, reasons = is_valid_file(file_path)
        if not is_valid:
            ignored_files += 1
            if warn_skipped:
                log_user_warning(f"Skipping {file_path}:")
                for reason in reasons:
                    log_user_warning(f"\t- {reason}")
            continue
        try:
            successful_files += 1
            local_rel_path = file_path.relative_to(local_path).parent
            yield construct_file(
                file_path=file_path, sds_path=PurePosixPath(local_rel_path)
            )
        except FileNotFoundError:
            continue
    log_user(
        f"Discovered {successful_files:,}/{successful_files + ignored_files:,} "
        "valid files"
    )
    if warn_skipped:
        if ignored_files:
            log_user_warning(f"Ignored {ignored_files} invalid files in '{local_path}'")
        else:
            log_user(f"No invalid files found in '{local_path}'")


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
        directory=PurePosixPath("./sds-files/dry-run/"),
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


def generate_random_files(num_files: int) -> list[File]:
    """Calls generate_sample_file() to create a list of fabricated files."""
    sample_files = []
    for _ in range(num_files):
        file_obj = generate_sample_file(uuid.uuid4())
        sample_files.append(file_obj)
    return sample_files
