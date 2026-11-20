#!/usr/bin/env bash
# Pre-application gate before registry apply on the mothership (see federation-doctor preflight_apply).
set -euo pipefail

# shellcheck source=../lib/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/common.sh"
exec "${FEDERATION_ROOT}/scripts/bin/federation-doctor.sh" preflight_apply