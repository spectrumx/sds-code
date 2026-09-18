#!/usr/bin/env bash
set -euo pipefail

FEDERATION_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_ROOT="${FEDERATION_ROOT}/../gateway"
GATEWAY_ENV_SELECTION="${GATEWAY_ROOT}/scripts/env-selection.sh"
# shellcheck source=lib/common.sh
source "${FEDERATION_ROOT}/scripts/lib/common.sh"

ENV_SELECTION="${FEDERATION_ROOT}/scripts/env-selection.sh"
SDS_ENV_TYPE="$("${ENV_SELECTION}" env)"
COMPOSE_FILE="$("${ENV_SELECTION}" compose_file)"
SYNC_CONTAINER="$("${ENV_SELECTION}" sync_container)"

default_hostname_fqdn() {
	hostname -f 2>/dev/null || hostname
}

gateway_compose() {
	local compose_file=$1
	shift
	local gate_env env_file
	gate_env="$("${GATEWAY_ENV_SELECTION}" env)"
	env_file="$("${GATEWAY_ENV_SELECTION}" env_file)"
	docker compose -f "${GATEWAY_ROOT}/${compose_file}" \
		--env-file "${GATEWAY_ROOT}/${env_file}" \
		--env-file "${GATEWAY_ROOT}/.envs/${gate_env}/storage.env" \
		"$@"
}

prompt_site_identity() {
	if [[ "${SDS_ENV_TYPE}" == "production" ]]; then
		ask SDS_SITE_FQDN "Public FQDN for this site" "$(default_hostname_fqdn)"
		ask SDS_SITE_NAME "Short site id (federation.toml [site].name)" "${SDS_SITE_FQDN%%.*}"
		ask SDS_SITE_DISPLAY_NAME "Human-readable site name" "${SDS_SITE_NAME}"
		ask FEDERATION_PEER_FQDN "Peer sync FQDN to bootstrap from" "sds.crc.nd.edu"
		ask FEDERATION_PEER_CA_PATH "Peer private CA bundle path (blank = omit ca_cert_path)" ""
	else
		ask SDS_SITE_FQDN "Site FQDN (OpenSearch site_name)" "sds.localhost"
		ask SDS_SITE_NAME "Short site id (federation.toml [site].name)" "crc"
		ask SDS_SITE_DISPLAY_NAME "Human-readable site name" "Local CRC"
		info "Local [[peers]] use Docker DNS (peer → sds-federation-peer-sync); see federation.peer.toml for reciprocal peer config"
	fi
	export SDS_SITE_FQDN SDS_SITE_NAME SDS_SITE_DISPLAY_NAME
	export FEDERATION_PEER_FQDN FEDERATION_PEER_CA_PATH
}

ensure_secrets() {
	if [[ -f "${FEDERATION_ROOT}/../federation-shared.env" ]]; then
		return 0
	fi
	info "Generating gateway secrets (${SDS_ENV_TYPE})"
	( cd "${GATEWAY_ROOT}" && "./scripts/generate-secrets.sh" "${SDS_ENV_TYPE}" )
}

init_sync_token() {
	local container compose_file
	case "${SDS_ENV_TYPE}" in
	production)
		container="sds-gateway-prod-app"
		compose_file="compose.production.yaml"
		;;
	*)
		container="sds-gateway-local-app"
		compose_file="compose.local.yaml"
		;;
	esac
	info "Ensuring federation sync DRF token in gateway DB"
	gateway_compose "${compose_file}" exec -T "${container}" \
		uv run manage.py init_federation_sync_token
}

public_sync_health_url() {
	local base="${FEDERATION_SYNC_SERVICE_URL:-}"
	if [[ -z "${base}" && -f "${FEDERATION_ROOT}/site.env" ]]; then
		# shellcheck disable=SC1090
		source "${FEDERATION_ROOT}/site.env"
	fi
	base="${FEDERATION_SYNC_SERVICE_URL:-}"
	base="${base%/}"
	printf '%s/health\n' "${base}"
}

print_peer_handoff() {
	if [[ "${SDS_ENV_TYPE}" != "production" ]]; then
		cat <<EOF

--- Local peer mesh: ensure federation.peer.toml points crc → local sync ---

[[peers]]
name = "${SDS_SITE_NAME}"
fqdn = "${SDS_SITE_FQDN}"
display_name = "${SDS_SITE_DISPLAY_NAME}"
gateway_api_base = "http://sds-gateway-local-app:8000/api/v1"
sync_service_url = "http://sds-federation-local-sync:8000/sync"

Then: just deploy-local-peer-2-peer

EOF
		return 0
	fi
	cat <<EOF

--- Peer operator: add reciprocal [[peers]] and restart sync ---

[[peers]]
name = "${SDS_SITE_NAME}"
fqdn = "${SDS_SITE_FQDN}"
display_name = "${SDS_SITE_DISPLAY_NAME}"
gateway_api_base = "https://${SDS_SITE_FQDN}/api/v1"
sync_service_url = "${FEDERATION_SYNC_SERVICE_URL}/"

EOF
}

main() {
	prompt_site_identity
	export SDS_SITE_NAME SDS_SITE_FQDN SDS_SITE_DISPLAY_NAME
	if [[ "${SDS_ENV_TYPE}" != "production" ]]; then
		export RENDER_TRAEFIK_SYNC="${RENDER_TRAEFIK_SYNC:-0}"
		export FEDERATION_DOCTOR_SKIP_DNS="${FEDERATION_DOCTOR_SKIP_DNS:-1}"
	fi
	"${FEDERATION_ROOT}/scripts/render-site-config.sh"
	FEDERATION_DOCTOR_SKIP_DB=1 "${FEDERATION_ROOT}/scripts/federation-doctor.sh"
	ensure_secrets

	local gateway_health
	case "${SDS_ENV_TYPE}" in
	production) gateway_health="https://${SDS_SITE_FQDN}/" ;;
	*) gateway_health="${GATEWAY_URL:-http://localhost:8000}/" ;;
	esac
	wait_http_ok "${gateway_health}" "gateway"

	init_sync_token
	FEDERATION_DOCTOR_SKIP_DB=0 "${FEDERATION_ROOT}/scripts/federation-doctor.sh"

	info "Building and starting federation sync"
	(
		cd "${FEDERATION_ROOT}"
		COMPOSE_FILE="${COMPOSE_FILE}" docker compose build
		COMPOSE_FILE="${COMPOSE_FILE}" docker compose up -d --remove-orphans
	)

	local health_url
	health_url="$(public_sync_health_url)"
	wait_sync_operational "${health_url}" "public sync"
	restart_and_wait_sync "${SYNC_CONTAINER}" "${health_url}" "public sync"

	"${FEDERATION_ROOT}/scripts/federation-doctor.sh"
	print_peer_handoff
	info "Federation onboard complete"
}

main "$@"
