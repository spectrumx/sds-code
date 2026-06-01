#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

npx fallow dupes --format json -q | jq -e '
  [ (.clone_groups // .dupes.clone_groups // [])[]
    | select((.instances | map(.file) | unique | length) > 1)
  ] | length == 0
' >/dev/null

echo "No cross-file clone groups detected."
