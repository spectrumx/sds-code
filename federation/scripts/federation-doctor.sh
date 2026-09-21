#!/usr/bin/env bash
set -euo pipefail

FEDERATION_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib/common.sh
source "${FEDERATION_ROOT}/scripts/lib/common.sh"

ENV_SELECTION="${FEDERATION_ROOT}/scripts/env-selection.sh"
SDS_ENV_TYPE="$("${ENV_SELECTION}" env)"
GATEWAY_ROOT="${FEDERATION_ROOT}/../gateway"
FEDERATION_TOML="${FEDERATION_DOCTOR_FEDERATION_TOML:-${FEDERATION_ROOT}/federation.toml}"
DJANGO_ENV="${FEDERATION_DOCTOR_DJANGO_ENV:-${GATEWAY_ROOT}/.envs/${SDS_ENV_TYPE}/django.env}"
SHARED_ENV="${FEDERATION_DOCTOR_SHARED_ENV:-${FEDERATION_ROOT}/../federation-shared.env}"
SITE_ENV="${FEDERATION_DOCTOR_SITE_ENV:-${FEDERATION_ROOT}/site.env}"

FAILURES=0

record_fail() {
	printf 'FAIL: %s\n' "$*" >&2
	FAILURES=$((FAILURES + 1))
}

toml_site_value() {
	local key=$1 line
	line="$(grep -E "^${key}[[:space:]]*=" "${FEDERATION_TOML}" 2>/dev/null | head -1)" || true
	[[ -n "${line}" ]] || return 0
	sed -E 's/^[^=]+=[[:space:]]*"([^"]*)".*/\1/' <<<"${line}"
}

strip_env_file_rhs() {
	local raw=$1
	if [[ "${raw}" == \"*\" && "${raw}" == *\" ]]; then
		raw="${raw:1:${#raw}-2}"
		raw="${raw//\\\"/\"}"
		raw="${raw//\\\\/\\}"
	fi
	printf '%s\n' "${raw}"
}

env_value() {
	local file=$1 key=$2 line raw
	line="$(grep -E "^${key}=" "${file}" 2>/dev/null | tail -1)" || return 0
	[[ -n "${line}" ]] || return 0
	raw="${line#*=}"
	strip_env_file_rhs "${raw}"
}

check_identity() {
	local toml_name toml_fqdn env_name env_fqdn
	toml_name="$(toml_site_value name)"
	toml_fqdn="$(toml_site_value fqdn)"
	env_name="$(env_value "${DJANGO_ENV}" FEDERATION_SITE_NAME)"
	env_fqdn="$(env_value "${DJANGO_ENV}" SDS_SITE_FQDN)"
	[[ -n "${toml_name}" ]] || record_fail "federation.toml [site].name missing"
	[[ -n "${toml_fqdn}" ]] || record_fail "federation.toml [site].fqdn missing"
	if [[ -n "${env_name}" && "${toml_name}" != "${env_name}" ]]; then
		record_fail "federation.toml name (${toml_name}) != FEDERATION_SITE_NAME (${env_name})"
	fi
	if [[ -n "${env_fqdn}" && "${toml_fqdn}" != "${env_fqdn}" ]]; then
		record_fail "federation.toml fqdn (${toml_fqdn}) != SDS_SITE_FQDN (${env_fqdn})"
	fi
}

check_token() {
	local token
	token="$(env_value "${SHARED_ENV}" FEDERATION_SYNC_DRF_TOKEN)"
	if [[ -z "${token}" ]]; then
		record_fail "FEDERATION_SYNC_DRF_TOKEN missing in federation-shared.env"
		return
	fi
	if [[ "${#token}" -ne 40 ]]; then
		record_fail "FEDERATION_SYNC_DRF_TOKEN must be 40 characters (got ${#token})"
	fi
}

gateway_app_container() {
	case "${SDS_ENV_TYPE}" in
	production) printf '%s\n' "sds-gateway-prod-app" ;;
	*) printf '%s\n' "sds-gateway-local-app" ;;
	esac
}

check_db_token() {
	local token container
	token="$(env_value "${SHARED_ENV}" FEDERATION_SYNC_DRF_TOKEN)"
	[[ -n "${token}" ]] || return 0
	if [[ "${FEDERATION_DOCTOR_SKIP_DB:-0}" == "1" ]]; then
		return 0
	fi
	container="$(gateway_app_container)"
	if ! docker ps --format '{{.Names}}' | grep -qx "${container}"; then
		info "Skipping DB token check (${container} not running)"
		return 0
	fi
	if ! docker exec "${container}" uv run manage.py shell -c "
from rest_framework.authtoken.models import Token
print(Token.objects.filter(key='${token}').exists())
" 2>/dev/null | grep -qx True; then
		record_fail "FEDERATION_SYNC_DRF_TOKEN not present in gateway DB — run init_federation_sync_token"
	fi
}

check_networks() {
	local net
	for net in sds-network-prod sds-gateway-prod-opensearch-net; do
		if [[ "${SDS_ENV_TYPE}" != "production" ]]; then
			return 0
		fi
		if ! docker network inspect "${net}" >/dev/null 2>&1; then
			record_fail "docker network ${net} missing"
		fi
	done
}

check_dns() {
	local fqdn
	fqdn="$(toml_site_value fqdn)"
	[[ -n "${fqdn}" ]] || return 0
	if [[ "${FEDERATION_DOCTOR_SKIP_DNS:-0}" == "1" ]]; then
		return 0
	fi
	if ! getent hosts "${fqdn}" >/dev/null 2>&1; then
		record_fail "DNS does not resolve ${fqdn}"
	fi
}

check_ca() {
	# shellcheck source=lib/ca_cert_path.sh
	source "${FEDERATION_ROOT}/scripts/lib/ca_cert_path.sh"
	local configured host_path
	while IFS= read -r configured; do
		[[ -n "${configured}" ]] || continue
		host_path="$(ca_cert_host_path_for_check "${configured}")"
		if [[ ! -r "${host_path}" ]]; then
			record_fail "ca_cert_path ${configured} not readable on host at ${host_path} (PEM must be under federation/certs/)"
		fi
	done < <(grep -E 'ca_cert_path[[:space:]]*=' "${FEDERATION_TOML}" 2>/dev/null | sed -E 's/.*"([^"]+)".*/\1/' || true)
}

check_sync_url() {
	local url
	url="$(toml_site_value sync_service_url)"
	if [[ -z "${url}" ]]; then
		url="$(env_value "${SITE_ENV}" FEDERATION_SYNC_SERVICE_URL)"
	fi
	[[ -n "${url}" ]] || record_fail "sync_service_url / FEDERATION_SYNC_SERVICE_URL unset"
	if [[ "${url}" != https://* && "${SDS_ENV_TYPE}" == "production" ]]; then
		record_fail "production sync_service_url should be https (${url})"
	fi
	if [[ "${SDS_ENV_TYPE}" == "production" && "${url}" == *:8001* ]]; then
		record_fail "sync_service_url must not advertise host port :8001 (${url})"
	fi
}

check_doc_site() {
	local fqdn short
	fqdn="$(toml_site_value fqdn)"
	short="$(toml_site_value name)"
	[[ -n "${fqdn}" && -n "${short}" ]] || return 0
	if [[ "${FEDERATION_DOCTOR_SKIP_OPENSEARCH:-1}" == "1" ]]; then
		return 0
	fi
	# Optional live OpenSearch probe when federation sync container is up.
	local sync_container
	sync_container="$("${ENV_SELECTION}" sync_container)"
	if ! docker ps --format '{{.Names}}' | grep -qx "${sync_container}"; then
		return 0
	fi
	info "check_doc_site: live OpenSearch scan not implemented (set FEDERATION_DOCTOR_SKIP_OPENSEARCH=0 to enable later)"
}

run_check() {
	local name=$1
	info "check_${name}"
	"check_${name}"
}

main() {
	local only=${1:-}
	require_file "${FEDERATION_TOML}"
	if [[ -n "${only}" ]]; then
		run_check "${only}"
	else
		for c in identity token db_token networks dns ca sync_url doc_site; do
			run_check "${c}"
		done
	fi
	if ((FAILURES > 0)); then
		die "${FAILURES} check(s) failed"
	fi
	info "All checks passed"
}

if [[ -n "${FEDERATION_DOCTOR_CHECK:-}" ]]; then
	main "${FEDERATION_DOCTOR_CHECK}"
else
	main "${1:-}"
fi
