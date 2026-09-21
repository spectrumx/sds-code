#!/usr/bin/env bash
# Render site.env, federation.toml, gateway django federation block, optional Traefik drop-in.
set -euo pipefail

FEDERATION_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/common.sh
source "${FEDERATION_ROOT}/scripts/lib/common.sh"

ENV_SELECTION="${FEDERATION_ROOT}/scripts/env-selection.sh"
SDS_ENV_TYPE="$("${ENV_SELECTION}" env)"
COMPOSE_FILE="$("${ENV_SELECTION}" compose_file)"
FEDERATION_SYNC_CONTAINER="$("${ENV_SELECTION}" sync_container)"

export SDS_ENV_TYPE FEDERATION_SYNC_CONTAINER

default_gateway_internal() {
	case "${SDS_ENV_TYPE}" in
	production)
		printf '%s\n' "http://sds-gateway-prod-app:18000/api/v1"
		;;
	*)
		printf '%s\n' "http://sds-gateway-local-app:8000/api/v1"
		;;
	esac
}

default_redis_url() {
	case "${SDS_ENV_TYPE}" in
	production)
		printf '%s\n' "redis://sds-gateway-prod-redis:6379/0"
		;;
	*)
		printf '%s\n' "redis://sds-gateway-local-redis:6379/0"
		;;
	esac
}

default_sync_health_url() {
	printf 'http://%s:8000/sync/health\n' "${FEDERATION_SYNC_CONTAINER}"
}

default_peer_values() {
	case "${SDS_ENV_TYPE}" in
	production)
		export FEDERATION_PEER_NAME="${FEDERATION_PEER_NAME:-crc}"
		export FEDERATION_PEER_FQDN="${FEDERATION_PEER_FQDN:-sds.crc.nd.edu}"
		export FEDERATION_PEER_DISPLAY_NAME="${FEDERATION_PEER_DISPLAY_NAME:-Notre Dame CRC}"
		export FEDERATION_PEER_GATEWAY_API_BASE="${FEDERATION_PEER_GATEWAY_API_BASE:-https://${FEDERATION_PEER_FQDN}/api/v1}"
		export FEDERATION_PEER_SYNC_SERVICE_URL="${FEDERATION_PEER_SYNC_SERVICE_URL:-https://${FEDERATION_PEER_FQDN}/sync/}"
		;;
	*)
		# Same-machine p2p (compose.peer.local.yaml): Docker DNS, not Traefik.
		export FEDERATION_PEER_NAME="${FEDERATION_PEER_NAME:-peer}"
		export FEDERATION_PEER_FQDN="${FEDERATION_PEER_FQDN:-peer.local}"
		export FEDERATION_PEER_DISPLAY_NAME="${FEDERATION_PEER_DISPLAY_NAME:-Local Peer}"
		export FEDERATION_PEER_GATEWAY_API_BASE="${FEDERATION_PEER_GATEWAY_API_BASE:-http://sds-gateway-local-app:8000/api/v1}"
		export FEDERATION_PEER_SYNC_SERVICE_URL="${FEDERATION_PEER_SYNC_SERVICE_URL:-http://sds-federation-peer-sync:8000/sync}"
		;;
	esac
}

export_vars_for_render() {
	export SDS_SITE_NAME SDS_SITE_FQDN SDS_SITE_DISPLAY_NAME
	export FEDERATION_SYNC_SERVICE_URL
	export GATEWAY_INTERNAL_BASE_URL="${GATEWAY_INTERNAL_BASE_URL:-$(default_gateway_internal)}"
	export REDIS_URL="${REDIS_URL:-$(default_redis_url)}"
	export FEDERATION_SYNC_HEALTH_URL="${FEDERATION_SYNC_HEALTH_URL:-$(default_sync_health_url)}"
	export FEDERATION_SYNC_USER_EMAIL="${FEDERATION_SYNC_USER_EMAIL:-federation-sync@internal.local}"
	default_peer_values
}

envsubst_file() {
	local template=$1 dest=$2
	envsubst <"${template}" >"${dest}"
}

merge_env_block_into() {
	local block_file=$1 target=$2
	require_file "${block_file}"
	if [[ ! -f "${target}" ]]; then
		cp "${block_file}" "${target}"
		return 0
	fi
	local tmp
	tmp="$(mktemp)"
	python3 - "${block_file}" "${target}" "${tmp}" <<'PY'
import sys
from pathlib import Path

block_path, target_path, out_path = sys.argv[1:4]
block = {}
for line in Path(block_path).read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        continue
    k, v = line.split("=", 1)
    block[k] = v

lines = Path(target_path).read_text().splitlines()
keys = set(block)
out = []
seen = set()
for line in lines:
    stripped = line.strip()
    if stripped and not stripped.startswith("#") and "=" in stripped:
        k = stripped.split("=", 1)[0]
        if k in keys:
            out.append(f"{k}={block[k]}")
            seen.add(k)
            continue
    out.append(line)
for k, v in block.items():
    if k not in seen:
        out.append(f"{k}={v}")
Path(out_path).write_text("\n".join(out) + "\n")
PY
	mv "${tmp}" "${target}"
}

append_peer_ca_cert() {
	local toml=$1 container_path
	if [[ -z "${FEDERATION_PEER_CA_PATH:-}" ]]; then
		return 0
	fi
	# shellcheck source=lib/ca_cert_path.sh
	source "${FEDERATION_ROOT}/scripts/lib/ca_cert_path.sh"
	container_path="$(ca_cert_container_path_from_input "${FEDERATION_PEER_CA_PATH}")"
	printf 'ca_cert_path = "%s"\n' "${container_path}" >>"${toml}"
}

merge_federation_toml_peers() {
	local rendered=$1 existing=$2 out=$3
	python3 "${FEDERATION_ROOT}/scripts/merge_federation_toml_peers.py" \
		"${rendered}" "${existing}" "${out}"
}

render_federation_toml() {
	local dest="${FEDERATION_ROOT}/federation.toml"
	local rendered tmp
	rendered="$(mktemp)"
	envsubst_file "${FEDERATION_ROOT}/templates/federation.toml.tmpl" "${rendered}"
	append_peer_ca_cert "${rendered}"
	if [[ ! -f "${dest}" ]]; then
		mv "${rendered}" "${dest}"
		return 0
	fi
	tmp="$(mktemp)"
	merge_federation_toml_peers "${rendered}" "${dest}" "${tmp}"
	mv "${tmp}" "${dest}"
	rm -f "${rendered}"
}

render_site_env() {
	envsubst_file "${FEDERATION_ROOT}/templates/site.env.tmpl" "${FEDERATION_ROOT}/site.env"
}

render_gateway_federation_env() {
	local django_env="${FEDERATION_ROOT}/../gateway/.envs/${SDS_ENV_TYPE}/django.env"
	local block
	block="$(mktemp)"
	envsubst_file "${FEDERATION_ROOT}/templates/gateway-federation.env.tmpl" "${block}"
	merge_env_block_into "${block}" "${django_env}"
	rm -f "${block}"
}

traefik_sync_route_exists_for_fqdn() {
	local fqdn=$1 conf_dir=$2
	# Gateway catch-alls use Host() only; federation sync requires PathPrefix(`/sync`).
	local host_path='Host\(`'"${fqdn}"'`\)[[:space:]]*&&[[:space:]]*PathPrefix\(`/sync`\)'
	[[ -d "${conf_dir}" ]] && grep -rqE "${host_path}" "${conf_dir}" 2>/dev/null
}

render_traefik_sync_dropin() {
	local conf_dir="${FEDERATION_ROOT}/../network/traefik/conf.d"
	if traefik_sync_route_exists_for_fqdn "${SDS_SITE_FQDN}" "${conf_dir}"; then
		info "Traefik already routes ${SDS_SITE_FQDN}/sync (skipping drop-in)"
		return 0
	fi
	mkdir -p "${conf_dir}"
	local dest="${conf_dir}/${SDS_SITE_NAME}-sync.toml"
	export TRAEFIK_SYNC_ROUTER_ID="sds-site-${SDS_SITE_NAME}-sync"
	envsubst_file "${FEDERATION_ROOT}/templates/traefik-sync.toml.tmpl" "${dest}"
	info "Wrote ${dest}"
}

main() {
	export_vars_for_render
	[[ -n "${SDS_SITE_NAME:-}" && -n "${SDS_SITE_FQDN:-}" ]] \
		|| die "SDS_SITE_NAME and SDS_SITE_FQDN must be set"
	export SDS_SITE_DISPLAY_NAME="${SDS_SITE_DISPLAY_NAME:-${SDS_SITE_NAME}}"
	if [[ -z "${FEDERATION_SYNC_SERVICE_URL:-}" ]]; then
		if [[ "${SDS_ENV_TYPE}" == "production" ]]; then
			export FEDERATION_SYNC_SERVICE_URL="https://${SDS_SITE_FQDN}/sync"
		else
			export FEDERATION_SYNC_SERVICE_URL="http://localhost:8001/sync"
		fi
	fi
	render_site_env
	render_federation_toml
	render_gateway_federation_env
	if [[ "${RENDER_TRAEFIK_SYNC:-1}" == "1" ]]; then
		render_traefik_sync_dropin
	fi
	info "Rendered site.env, federation.toml, gateway federation env (${SDS_ENV_TYPE})"
}

main "$@"
