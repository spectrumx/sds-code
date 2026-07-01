#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

LOCAL_FALLOW="node_modules/.bin/fallow"
if [[ -x "${LOCAL_FALLOW}" ]]; then
	"${LOCAL_FALLOW}" dupes --format json -q | jq -e '
  [ (.clone_groups // .dupes.clone_groups // [])[]
    | select((.instances | map(.file) | unique | length) > 1)
  ] | length == 0
' >/dev/null
else
	# Use first available: vpx > bunx > npx (avoid pnpx; global pnpm may need newer Node)
	if command -v vpx &>/dev/null; then
		RUNNER=(vpx)
	elif command -v bunx &>/dev/null; then
		RUNNER=(bunx)
	elif command -v npx &>/dev/null; then
		RUNNER=(npx)
	else
		echo "Error: neither local fallow, vpx, bunx, nor npx found" >&2
		exit 1
	fi

	"${RUNNER[@]}" fallow dupes --format json -q | jq -e '
  [ (.clone_groups // .dupes.clone_groups // [])[]
    | select((.instances | map(.file) | unique | length) > 1)
  ] | length == 0
' >/dev/null
fi

echo "No cross-file clone groups detected."
