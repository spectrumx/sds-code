#!/usr/bin/env python3
"""Write federation/site.env with double-quoted values safe for bash source and compose."""

from __future__ import annotations

import os
import sys
from pathlib import Path

SITE_ENV_KEYS = (
    "SDS_SITE_NAME",
    "SDS_SITE_FQDN",
    "SDS_SITE_DISPLAY_NAME",
    "FEDERATION_SYNC_SERVICE_URL",
    "GATEWAY_INTERNAL_BASE_URL",
    "REDIS_URL",
    "FEDERATION_PEER_CA_PATH",
)


def quote_shell_value(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
    )
    return f'"{escaped}"'


def render_site_env_lines() -> list[str]:
    lines = [
        f"{key}={quote_shell_value(os.environ.get(key, ''))}" for key in SITE_ENV_KEYS
    ]
    lines.append(
        "# Host path under federation/certs/ (optional; re-render uses this when unset in the shell)"
    )
    return lines


def write_site_env(dest: Path | str) -> None:
    Path(dest).write_text("\n".join(render_site_env_lines()) + "\n")


def main() -> None:
    write_site_env(sys.argv[1])


if __name__ == "__main__":
    main()
