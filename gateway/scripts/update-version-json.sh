#!/usr/bin/env bash
# Update gateway/version.json with current git metadata.
#
# Called from:
#   - pre-commit hook (via .pre-commit-config.yaml)
#   - just build / just build-full (via gateway/justfile)
#
# The script derives all paths from its own location so it works regardless
# of the caller's working directory.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_JSON="${SCRIPT_DIR}/../version.json"

# --- Collect metadata ---
COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")"

if VERSION="$(git describe --tags --always 2>/dev/null)"; then
	: # VERSION already set
else
	VERSION="$COMMIT"
fi

BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# --- Write version.json ---
cat >"$VERSION_JSON" <<EOF
{
	"commit": "${COMMIT}",
	"version": "${VERSION}",
	"build_date": "${BUILD_DATE}"
}
EOF
