#!/usr/bin/env bash
set -euo pipefail

FEDERATION_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/common.sh
source "${FEDERATION_ROOT}/scripts/lib/common.sh"

ENV_SELECTION="${FEDERATION_ROOT}/scripts/env-selection.sh"
SYNC_CONTAINER="$("${ENV_SELECTION}" sync_container)"
FEDERATION_TOML="${FEDERATION_ROOT}/federation.toml"

public_sync_health_url_from_env() {
	local base="${FEDERATION_SYNC_SERVICE_URL:-}"
	base="${base%/}"
	printf '%s/health\n' "${base}"
}

usage() {
	die "usage: $0 --name NAME --fqdn FQDN [--display-name NAME] [--gateway-api-base URL] [--sync-url URL] [--ca-cert-path PATH]"
}

while [[ $# -gt 0 ]]; do
	case "$1" in
	--name) PEER_NAME=$2; shift 2 ;;
	--fqdn) PEER_FQDN=$2; shift 2 ;;
	--display-name) PEER_DISPLAY=$2; shift 2 ;;
	--gateway-api-base) PEER_GATEWAY=$2; shift 2 ;;
	--sync-url) PEER_SYNC=$2; shift 2 ;;
	--ca-cert-path) PEER_CA=$2; shift 2 ;;
	-h | --help) usage ;;
	*) die "unknown argument: $1" ;;
	esac
done

[[ -n "${PEER_NAME:-}" && -n "${PEER_FQDN:-}" ]] || usage
PEER_DISPLAY="${PEER_DISPLAY:-${PEER_NAME}}"
PEER_GATEWAY="${PEER_GATEWAY:-https://${PEER_FQDN}/api/v1}"
PEER_SYNC="${PEER_SYNC:-https://${PEER_FQDN}/sync/}"

require_file "${FEDERATION_TOML}"
if grep -q "fqdn = \"${PEER_FQDN}\"" "${FEDERATION_TOML}"; then
	die "peer ${PEER_FQDN} already present in federation.toml"
fi

peer_ca_toml_line() {
	[[ -n "${PEER_CA:-}" ]] || return 0
	# shellcheck source=lib/ca_cert_path.sh
	source "${FEDERATION_ROOT}/scripts/lib/ca_cert_path.sh"
	local container_path
	container_path="$(ca_cert_container_path_from_input "${PEER_CA}")"
	printf 'ca_cert_path = "%s"\n' "${container_path}"
}

{
	printf '\n[[peers]]\n'
	printf 'name = "%s"\n' "${PEER_NAME}"
	printf 'fqdn = "%s"\n' "${PEER_FQDN}"
	printf 'display_name = "%s"\n' "${PEER_DISPLAY}"
	printf 'gateway_api_base = "%s"\n' "${PEER_GATEWAY}"
	printf 'sync_service_url = "%s"\n' "${PEER_SYNC}"
	peer_ca_toml_line
} >>"${FEDERATION_TOML}"

info "Restarting ${SYNC_CONTAINER}"
docker restart "${SYNC_CONTAINER}" >/dev/null

SITE_ENV_FILE="${FEDERATION_ROOT}/site.env"
if [[ -f "${SITE_ENV_FILE}" ]]; then
	# shellcheck disable=SC1090
	source "${SITE_ENV_FILE}"
fi
SYNC_HEALTH="$(public_sync_health_url_from_env)"
if [[ -z "${FEDERATION_SYNC_SERVICE_URL:-}" ]]; then
	SYNC_HEALTH="http://127.0.0.1:8001/sync/health"
fi

wait_sync_operational "${SYNC_HEALTH}" "sync after peer add"
info "Peer ${PEER_NAME} (${PEER_FQDN}) added — confirm peer site_name in fed-datasets"
