def validate_file_permission_string(permissions: str) -> None:
    """Make sure a unix-like permissions string is valid."""
    perm_flags_len = 9
    assert (
        len(permissions) == perm_flags_len
    ), "Invalid permissions string. Expected 9 characters."
    valid_chars = {"r", "w", "x", "-"}
    assert set(permissions).issubset(
        valid_chars,
    ), "Invalid permission characters: use 'r', 'w', 'x', or '-'"
    assert all(
        permissions[idx * 3] in {"r", "-"} for idx in range(3)
    ), "Invalid read permissions"
    assert all(
        permissions[idx * 3 + 1] in {"w", "-"} for idx in range(3)
    ), "Invalid write permissions"
    assert all(
        permissions[idx * 3 + 2] in {"x", "-"} for idx in range(3)
    ), "Invalid execute permissions"
