"""Tests for the permission model functions."""

import pytest
from spectrumx.models.files.permission import PermissionRepresentation
from spectrumx.models.files.permission import octal_to_unix_perm_string
from spectrumx.models.files.permission import unix_perm_from_any
from spectrumx.models.files.permission import unix_perm_string_to_octal


class TestOctalToUnixPermString:
    """Tests for octal_to_unix_perm_string."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0, "---------"),
            (0o644, "rw-r--r--"),
            (0o700, "rwx------"),
            (0o755, "rwxr-xr-x"),
            (511, "rwxrwxrwx"),
        ],
        ids=["zero", "644", "700", "755", "full"],
    )
    def test_octal_to_unix_perm_string(self, value: int, expected: str) -> None:
        """octal_to_unix_perm_string covers per-trit branches."""
        assert octal_to_unix_perm_string(value) == expected


class TestUnixPermStringToOctal:
    """Tests for unix_perm_string_to_octal."""

    def test_no_permissions(self) -> None:
        """unix_perm_string_to_octal('---------') returns 0."""
        assert unix_perm_string_to_octal("---------") == 0

    def test_full_permissions(self) -> None:
        """unix_perm_string_to_octal('rwxrwxrwx') returns 511."""
        assert unix_perm_string_to_octal("rwxrwxrwx") == 0o777

    @pytest.mark.parametrize("value", range(512), ids=lambda v: f"o{v:03o}")
    def test_round_trip_all_octal_values(self, value: int) -> None:
        """Round-trip octal for all n in [0, 512)."""
        assert unix_perm_string_to_octal(octal_to_unix_perm_string(value)) == value


class TestUnixPermFromAny:
    """Tests for unix_perm_from_any."""

    def test_int_input(self) -> None:
        """unix_perm_from_any(0o755) returns 'rwxr-xr-x'."""
        assert unix_perm_from_any(0o755) == "rwxr-xr-x"

    def test_str_input(self) -> None:
        """unix_perm_from_any('rwxr-xr-x') returns 'rwxr-xr-x'."""
        assert unix_perm_from_any("rwxr-xr-x") == "rwxr-xr-x"

    def test_invalid_type_none_returns_value_error(self) -> None:
        """unix_perm_from_any returns a ValueError for a non-int, non-str input."""
        result = unix_perm_from_any(None)  # type: ignore[arg-type]
        assert isinstance(result, ValueError)
        assert "Invalid Unix permission format:" in str(result)

    def test_invalid_type_list_returns_value_error(self) -> None:
        """A list input returns a ValueError naming the invalid format."""
        result = unix_perm_from_any([1, 2, 3])  # type: ignore[arg-type]
        assert isinstance(result, ValueError)
        assert "Invalid Unix permission format:" in str(result)

    @pytest.mark.parametrize(
        "bad_string",
        ["rwxrwxrwxExtra", "rwxrwxr??", "rw-r--r--!", "short"],
        ids=["too_long", "bad_chars", "trailing_symbol", "too_short"],
    )
    def test_invalid_string_raises_value_error(self, bad_string: str) -> None:
        """An invalid permission string raises ValueError."""
        with pytest.raises(ValueError, match="validation error"):
            unix_perm_from_any(bad_string)


class TestPermissionRepresentation:
    """Tests for PermissionRepresentation enum."""

    def test_string_member(self) -> None:
        """PermissionRepresentation.STRING == 'string'."""
        assert PermissionRepresentation.STRING == "string"

    def test_octal_member(self) -> None:
        """PermissionRepresentation.OCTAL == 'octal'."""
        assert PermissionRepresentation.OCTAL == "octal"

    def test_missing_raises_value_error(self) -> None:
        """PermissionRepresentation._missing_() raises ValueError for unknown value."""
        with pytest.raises(ValueError, match="Invalid PermissionRepresentation value"):
            PermissionRepresentation("invalid_value")  # type: ignore[arg-type]
