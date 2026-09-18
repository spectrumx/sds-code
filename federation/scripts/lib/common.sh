#!/usr/bin/env bash
# Shared helpers for federation onboarding and local p2p deploy scripts.
set -euo pipefail

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '==> %s\n' "$*"; }

require_file() {
	[[ -f "$1" ]] || die "missing $1"
}

ask() {
	local __var=$1 __prompt=$2 __default=${3:-} __reply
	if [[ -n "${!__var:-}" ]]; then
		return 0
	fi
	read -rp "$(printf '%s%s: ' "${__prompt}" "${__default:+ [${__default}]}")" __reply
	printf -v "${__var}" '%s' "${__reply:-${__default}}"
}

ensure_docker_network() {
	local name=$1
	if docker network inspect "${name}" >/dev/null 2>&1; then
		return 0
	fi
	info "Creating docker network ${name}"
	docker network create --driver bridge "${name}" >/dev/null
}

wait_http_ok() {
	local url=$1 label=$2
	local wait_secs=${WAIT_SECS:-180}
	local deadline=$((SECONDS + wait_secs))
	info "Waiting for ${label} (${url})"
	while ((SECONDS < deadline)); do
		if curl -fsS -o /dev/null --max-time 3 "${url}"; then
			info "${label} is up"
			return 0
		fi
		sleep 2
	done
	die "${label} not healthy after ${wait_secs}s: ${url}"
}

# Require /sync/health JSON status == "ok" (not merely HTTP 200/503).
wait_sync_operational() {
	local url=$1 label=$2
	local wait_secs=${WAIT_SECS:-180}
	local deadline=$((SECONDS + wait_secs))
	local body
	info "Waiting for ${label} operational (${url})"
	while ((SECONDS < deadline)); do
		body="$(curl -fsS --max-time 3 "${url}" 2>/dev/null || true)"
		if [[ -n "${body}" ]] && printf '%s' "${body}" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'; then
			info "${label} operational"
			return 0
		fi
		sleep 2
	done
	die "${label} not operational after ${wait_secs}s: ${url}"
}

restart_and_wait_sync() {
	local container=$1 url=$2 label=$3
	info "Restarting ${container} so site-hello/bootstrap see a live peer"
	docker restart "${container}" >/dev/null
	wait_sync_operational "${url}" "${label}"
}
