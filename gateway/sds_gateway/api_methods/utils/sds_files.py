from pathlib import Path

from loguru import logger as log
from rest_framework.request import Request

from sds_gateway.users.models import User


def sanitize_path_rel_to_user(
    unsafe_path: str,
    request: Request | None = None,
    user: User | None = None,
) -> Path | None:
    """Ensures a path is safe by making it relative to the user's root in SDS.
    Args:
        unsafe_path:    The unsafe path.
        request:        The request object with `.user.email`. OR
        user:           The user that should own the path.
    Returns:
        A Path object if the path is safe,
        or None if it is not safe to continue.
    """
    files_dir = Path("/files/")
    if request is not None:
        user_root_path = files_dir / request.user.email
    elif user is not None:
        user_root_path = files_dir / user.email
    else:
        msg = "Either user or request must be provided."
        raise ValueError(msg)
    if not user_root_path.is_relative_to(files_dir):
        msg = (
            "INTERNAL ERROR: User root path is not a subdirectory "
            f"of '{files_dir}': '{user_root_path}'"
        )
        log.warning(msg)
        return None
    unsafe_concat_path = Path(
        f"{user_root_path}/{unsafe_path}",
        # needs to be a concatenation, as we want to remain under the user's files dir
    )
    user_rel_path = unsafe_concat_path.resolve(strict=False)
    if not user_rel_path.is_relative_to(user_root_path):
        return None
    return user_rel_path
