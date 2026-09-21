#!/usr/bin/env bash
set -euo pipefail

FEDERATION_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/common.sh
source "${FEDERATION_ROOT}/scripts/lib/common.sh"
# shellcheck source=lib/bootstrap.sh
source "${FEDERATION_ROOT}/scripts/lib/bootstrap.sh"
federation_script_init
# shellcheck source=lib/gateway.sh
source "${FEDERATION_ROOT}/scripts/lib/gateway.sh"
# shellcheck source=lib/site_env.sh
source "${FEDERATION_ROOT}/scripts/lib/site_env.sh"

default_hostname_fqdn() {
	hostname -f 2>/dev/null || hostname
}

prompt_site_identity() {
	if [[ "${SDS_ENV_TYPE}" == "production" ]]; then
		ask SDS_SITE_FQDN "Public FQDN for this site" "$(default_hostname_fqdn)"
		ask SDS_SITE_NAME "Short site id (federation.toml [site].name)" "${SDS_SITE_FQDN%%.*}"
		ask SDS_SITE_DISPLAY_NAME "Human-readable site name" "${SDS_SITE_NAME}"
		ask FEDERATION_PEER_FQDN "Peer sync FQDN to bootstrap from" "sds.crc.nd.edu"
		ask FEDERATION_PEER_CA_PATH "Peer CA PEM path under federation/certs/ (stored as /etc/sds/certs/... in toml; blank = omit)" ""
	else
		ask SDS_SITE_FQDN "Site FQDN (OpenSearch site_name)" "sds.localhost"
		ask SDS_SITE_NAME "Short site id (federation.toml [site].name)" "crc"
		ask SDS_SITE_DISPLAY_NAME "Human-readable site name" "Local CRC"
		info "Local [[peers]] use Docker DNS (peer → sds-federation-peer-sync); see federation.peer.toml for reciprocal peer config"
	fi
	export SDS_SITE_FQDN SDS_SITE_NAME SDS_SITE_DISPLAY_NAME
	export FEDERATION_PEER_FQDN FEDERATION_PEER_CA_PATH
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
sync_service_url = "${FEDERATION_SYNC_SERVICE_URL%/}/"

EOF
}

main() {
	prompt_site_identity
	export SDS_SITE_NAME SDS_SITE_FQDN SDS_SITE_DISPLAY_NAME
	load_site_env_for_render
	if [[ "${SDS_ENV_TYPE}" != "production" ]]; then
		export RENDER_TRAEFIK_SYNC="${RENDER_TRAEFIK_SYNC:-0}"
		export FEDERATION_DOCTOR_SKIP_DNS="${FEDERATION_DOCTOR_SKIP_DNS:-1}"
	fi
	ensure_gateway_secrets
	"${FEDERATION_ROOT}/scripts/render-site-config.sh"
	load_rendered_site_env
	FEDERATION_DOCTOR_SKIP_DB=1 "${FEDERATION_ROOT}/scripts/federation-doctor.sh"
	recreate_gateway_for_updated_env

	wait_gateway_app_ready

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
