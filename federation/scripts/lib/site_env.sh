#!/usr/bin/env bash
# Requires FEDERATION_ROOT.

load_site_env_file() {
	local site_env="${FEDERATION_ROOT}/site.env"
	[[ -f "${site_env}" ]] || return 0
	# shellcheck disable=SC1090
	source "${site_env}"
}

# Restore persisted onboarding vars when re-rendering without exports in the shell.
load_site_env_for_render() {
	if [[ -n "${FEDERATION_PEER_CA_PATH:-}" ]]; then
		return 0
	fi
	load_site_env_file
}

load_rendered_site_env() {
	load_site_env_file
	export FEDERATION_SYNC_SERVICE_URL
}

public_sync_health_url() {
	local base
	if [[ -z "${FEDERATION_SYNC_SERVICE_URL:-}" ]]; then
		load_rendered_site_env
	fi
	base="${FEDERATION_SYNC_SERVICE_URL:-}"
	if [[ -z "${base}" ]]; then
		printf '%s\n' "http://127.0.0.1:8001/sync/health"
		return 0
	fi
	base="${base%/}"
	printf '%s/health\n' "${base}"
}
