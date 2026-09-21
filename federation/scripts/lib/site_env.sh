#!/usr/bin/env bash
# Requires FEDERATION_ROOT.

site_env_path() {
	printf '%s/site.env\n' "${FEDERATION_ROOT}"
}

# Value from site.env (handles double-quoted lines from write_site_env.py).
site_env_value() {
	local key=$1
	local file line raw
	file="$(site_env_path)"
	[[ -f "${file}" ]] || return 0
	line="$(grep -E "^${key}=" "${file}" 2>/dev/null | tail -1)" || return 0
	[[ -n "${line}" ]] || return 0
	raw="${line#*=}"
	if [[ "${raw}" == \"*\" && "${raw}" == *\" ]]; then
		raw="${raw:1:${#raw}-2}"
		raw="${raw//\\\"/\"}"
		raw="${raw//\\\\/\\}"
	fi
	printf '%s\n' "${raw}"
}

load_site_env_file() {
	local site_env
	site_env="$(site_env_path)"
	[[ -f "${site_env}" ]] || return 0
	# shellcheck disable=SC1090
	source "${site_env}"
}

# Restore persisted optional vars when re-rendering; never override exported identity.
load_site_env_for_render() {
	if [[ -n "${FEDERATION_PEER_CA_PATH:-}" ]]; then
		return 0
	fi
	local stored
	stored="$(site_env_value FEDERATION_PEER_CA_PATH)" || true
	[[ -n "${stored}" ]] || return 0
	export FEDERATION_PEER_CA_PATH="${stored}"
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
