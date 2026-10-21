#!/usr/bin/env bash
set -euo pipefail

FEDERATION_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/common.sh
source "${FEDERATION_ROOT}/scripts/lib/common.sh"
# shellcheck source=lib/bootstrap.sh
source "${FEDERATION_ROOT}/scripts/lib/bootstrap.sh"
federation_script_init
# shellcheck source=lib/site_env.sh
source "${FEDERATION_ROOT}/scripts/lib/site_env.sh"

FEDERATION_TOML="${FEDERATION_ROOT}/federation.toml"

usage() {
	die "usage: $0 --fqdn FQDN [--discover] [--name NAME] [--display-name NAME] [--gateway-api-base URL] [--sync-url URL] [--ca-cert-path PATH]"
}

DISCOVER=0
while [[ $# -gt 0 ]]; do
	case "$1" in
	--name) PEER_NAME=$2; shift 2 ;;
	--fqdn) PEER_FQDN=$2; shift 2 ;;
	--display-name) PEER_DISPLAY=$2; shift 2 ;;
	--gateway-api-base) PEER_GATEWAY=$2; shift 2 ;;
	--sync-url) PEER_SYNC=$2; shift 2 ;;
	--ca-cert-path) PEER_CA=$2; shift 2 ;;
	--discover) DISCOVER=1; shift ;;
	-h | --help) usage ;;
	*) die "unknown argument: $1" ;;
	esac
done

[[ -n "${PEER_FQDN:-}" ]] || usage

if [[ "${DISCOVER}" -eq 1 ]]; then
	DISCOVER_SCRIPT="${FEDERATION_ROOT}/scripts/lib/discover_peer_well_known.py"
	require_file "${DISCOVER_SCRIPT}"
	DISCOVER_OUTPUT=""
	if ! DISCOVER_OUTPUT="$(python3 "${DISCOVER_SCRIPT}" "${PEER_FQDN}")"; then
		die "discover failed for https://${PEER_FQDN}/.well-known/sds-federation.json"
	fi
	while IFS= read -r line; do
		key="${line%%=*}"
		value="${line#*=}"
		case "${key}" in
		name) PEER_NAME="${value}" ;;
		fqdn) PEER_FQDN="${value}" ;;
		display_name) PEER_DISPLAY="${value}" ;;
		gateway_api_base) PEER_GATEWAY="${value}" ;;
		sync_service_url) PEER_SYNC="${value}" ;;
		*) die "unexpected discover output: ${line}" ;;
		esac
	done <<< "${DISCOVER_OUTPUT}"
	info "Discovered peer identity from https://${PEER_FQDN}/.well-known/sds-federation.json"
fi

[[ -n "${PEER_NAME:-}" ]] || die "--name is required (or use --discover)"
PEER_DISPLAY="${PEER_DISPLAY:-${PEER_NAME}}"
PEER_GATEWAY="${PEER_GATEWAY:-https://${PEER_FQDN}/api/v1}"
PEER_SYNC="${PEER_SYNC:-https://${PEER_FQDN}/sync/}"

require_file "${FEDERATION_TOML}"
if grep -q "fqdn = \"${PEER_FQDN}\"" "${FEDERATION_TOML}"; then
	die "peer ${PEER_FQDN} already present in federation.toml"
fi

PEER_CA_CONTAINER=""
if [[ -n "${PEER_CA:-}" ]]; then
	# shellcheck source=lib/ca_cert_path.sh
	source "${FEDERATION_ROOT}/scripts/lib/ca_cert_path.sh"
	PEER_CA_CONTAINER="$(ca_cert_container_path_from_input "${PEER_CA}")"
fi

{
	printf '\n[[peers]]\n'
	printf 'name = "%s"\n' "${PEER_NAME}"
	printf 'fqdn = "%s"\n' "${PEER_FQDN}"
	printf 'display_name = "%s"\n' "${PEER_DISPLAY}"
	printf 'gateway_api_base = "%s"\n' "${PEER_GATEWAY}"
	printf 'sync_service_url = "%s"\n' "${PEER_SYNC}"
	if [[ -n "${PEER_CA_CONTAINER}" ]]; then
		printf 'ca_cert_path = "%s"\n' "${PEER_CA_CONTAINER}"
	fi
} >>"${FEDERATION_TOML}"

info "Restarting ${SYNC_CONTAINER}"
docker restart "${SYNC_CONTAINER}" >/dev/null

load_rendered_site_env
SYNC_HEALTH="$(public_sync_health_url)"

wait_sync_operational "${SYNC_HEALTH}" "sync after peer add"
info "Peer ${PEER_NAME} (${PEER_FQDN}) added — confirm peer site_name in fed-datasets"
