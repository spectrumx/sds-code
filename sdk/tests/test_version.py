"""Tests versioning of SpectrumX."""

import re


def test_version_exists() -> None:
    """Tests the version of the SpectrumX SDK exists."""
    from spectrumx import __version__

    assert isinstance(__version__, str), "Version number must be a string"


def test_version_sem_ver() -> None:
    """Tests the version number follows semantic versioning.

    Following https://peps.python.org/pep-0440/#public-version-identifiers
    """
    from spectrumx import __version__

    sem_ver_pattern: re.Pattern[str] = re.compile(
        r"^\d+(\.\d+)*([abrc]\d+)?(\.post\d+)?(\.dev\d+)?$"
    )
    assert sem_ver_pattern.match(__version__), (
        "Version number must follow semantic versioning with optional "
        "pre-release, post-release, or dev-release segments"
    )


def test_version_pyproject() -> None:
    """Tests the version is the same as in pyproject.toml."""
    from importlib.metadata import version

    from spectrumx import __version__

    assert __version__ == version(
        "spectrumx",
    ), "Version number must match pyproject.toml"
