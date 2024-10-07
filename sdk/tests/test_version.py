"""
Tests for the SpectrumX client.
"""


def test_version_exists() -> None:
    """Tests the version of the SpectrumX SDK exists."""
    from spectrumx import __version__

    assert isinstance(__version__, str), "Version number must be a string"


def test_version_sem_ver() -> None:
    """Tests the version number follows semantic versioning."""
    from spectrumx import __version__

    parts = __version__.split(".")
    three_parts = 3
    assert len(parts) == three_parts, "Version number must have three parts"
    assert all(part.isdigit() for part in parts)


def test_version_pyproject() -> None:
    """Tests the version is the same as in pyproject.toml."""
    from importlib.metadata import version

    from spectrumx import __version__

    assert __version__ == version(
        "spectrumx",
    ), "Version number must match pyproject.toml"
