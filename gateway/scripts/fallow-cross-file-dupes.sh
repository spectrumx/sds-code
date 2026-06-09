#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Use first available: vpx > bunx > npx
if command -v pnpx &>/dev/null; then
	RUNNER=pnpx
elif command -v vpx &>/dev/null; then
	RUNNER=vpx
elif command -v bunx &>/dev/null; then
	RUNNER=bunx
elif command -v npx &>/dev/null; then
	RUNNER=npx
else
	echo "Error: neither vpx, bunx, nor npx found in PATH" >&2
	exit 1
fi

"${RUNNER}" fallow dupes --format json -q | jq -e '
  [ (.clone_groups // .dupes.clone_groups // [])[]
    | select((.instances | map(.file) | unique | length) > 1)
  ] | length == 0
' >/dev/null

echo "No cross-file clone groups detected."
