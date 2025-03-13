"""Tests for the Path models."""

# pylint: disable=redefined-outer-name

import textwrap
from pathlib import PureWindowsPath

import pytest
from mypy.api import run
from pydantic import TypeAdapter
from pydantic import ValidationError
from pydantic import validate_call
from spectrumx.models.files import SDSDirectory
from spectrumx.models.files import SDSDirectoryInput


def test_static_type_error():
    """Ensure that `use_path(PurePath(...))` fails statically."""
    code = textwrap.dedent("""
        from pydantic import TypeAdapter
        from pathlib import PureWindowsPath, PurePosixPath, PurePath, Path
        from spectrumx.models.files import SDSDirectory, SDSDirectoryInput

        def use_path(sds_path: SDSDirectoryInput) -> None:
            sds_directory = TypeAdapter(SDSDirectory).validate_python(sds_path)
            print(sds_directory / "test") # ✅ Should pass

        use_path("/my/upload/path")  # ✅ Should pass
        use_path(Path("/my/upload/path"))  # ✅ Should pass
        use_path(PurePath("/my/upload/path"))  # ✅ Should pass
        use_path(PurePosixPath("/my/upload/path"))  # ✅ Should pass
        use_path(PureWindowsPath("/my/upload/path"))  # ❌ Should FAIL statically
    """)

    stdout, stderr, exit_code = run(["-c", code, "--strict"])
    print(stdout)
    assert exit_code == 1

    errors = "\n".join([l for l in stdout.splitlines() if "error:" in l])
    assert 'Argument 1 to "use_path" has incompatible type "PureWindowsPath"' in errors


def test_static_type_error_sdsdirectory():
    """Ensure that `use_path(PurePath(...))` fails statically."""
    code = textwrap.dedent("""
        from typing import Union
        from pathlib import PureWindowsPath, PurePosixPath, PurePath, Path
        from pydantic import validate_call
        from spectrumx.models.files import SDSDirectory

        @validate_call
        def use_path(sds_path: SDSDirectory) -> None:
            print(sds_path / "test") # ✅ Should pass

        use_path("/my/upload/path")  # ✅ Should pass
        use_path(Path("/my/upload/path"))  # ✅ Should pass
        use_path(PurePath("/my/upload/path"))  # ✅ Should pass
        use_path(PurePosixPath("/my/upload/path"))  # ✅ Should pass
        use_path(PureWindowsPath("/my/upload/path"))  # ❌ Should FAIL statically
    """)

    stdout, stderr, exit_code = run(["-c", code, "--strict"])
    assert exit_code == 1

    lines = [l for l in stdout.splitlines() if "error:" in l]
    assert len(lines) == 1
    assert (
        'Argument 1 to "use_path" has incompatible type "PureWindowsPath"' in lines[0]
    )


def test_path_deserialization() -> None:
    @validate_call
    def use_path(sds_path: SDSDirectoryInput):
        sds_directory = TypeAdapter(SDSDirectory).validate_python(sds_path)

    # Empty paths shouldnt be allowed
    with pytest.raises(ValidationError):
        use_path("")

    # Long paths shouldnt be allowed
    with pytest.raises(ValidationError):
        use_path("a" * 5000)

    # Backslashes paths shouldnt be allowed
    with pytest.raises(ValidationError):
        use_path("\\")

    with pytest.raises(ValidationError):
        use_path(PureWindowsPath("."))
