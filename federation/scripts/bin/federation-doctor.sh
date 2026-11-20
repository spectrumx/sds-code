#!/usr/bin/env bash
set -euo pipefail

# shellcheck source=../lib/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/common.sh"
# shellcheck source=lib/traefik.sh
source "${FEDERATION_ROOT}/scripts/lib/traefik.sh"

ENV_SELECTION="${FEDERATION_ROOT}/scripts/lib/env-selection.sh"
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

normalize_fqdn() {
	local host=$1
	printf '%s\n' "${host}" | tr '[:upper:]' '[:lower:]' | sed 's/\.$//'
}

check_identity() {
	local toml_name toml_fqdn env_name env_fqdn site_fqdn site_name
	toml_name="$(toml_site_value name)"
	toml_fqdn="$(toml_site_value fqdn)"
	env_name="$(env_value "${DJANGO_ENV}" FEDERATION_SITE_NAME)"
	env_fqdn="$(env_value "${DJANGO_ENV}" SDS_SITE_FQDN)"
	site_fqdn="$(env_value "${SITE_ENV}" SDS_SITE_FQDN)"
	site_name="$(env_value "${SITE_ENV}" SDS_SITE_NAME)"
	[[ -n "${toml_name}" ]] || record_fail "federation.toml [site].name missing"
	[[ -n "${toml_fqdn}" ]] || record_fail "federation.toml [site].fqdn missing"
	if [[ -n "${env_name}" && "${toml_name}" != "${env_name}" ]]; then
		record_fail "federation.toml name (${toml_name}) != FEDERATION_SITE_NAME (${env_name})"
	fi
	if [[ -n "${env_fqdn}" && "${toml_fqdn}" != "${env_fqdn}" ]]; then
		record_fail "federation.toml fqdn (${toml_fqdn}) != SDS_SITE_FQDN (${env_fqdn})"
	fi
	if [[ -n "${site_fqdn}" && "$(normalize_fqdn "${toml_fqdn}")" != "$(normalize_fqdn "${site_fqdn}")" ]]; then
		record_fail "federation.toml fqdn (${toml_fqdn}) != SDS_SITE_FQDN in site.env (${site_fqdn})"
	fi
	if [[ -n "${site_name}" && -n "${toml_name}" && "${toml_name}" != "${site_name}" ]]; then
		record_fail "federation.toml name (${toml_name}) != SDS_SITE_NAME in site.env (${site_name})"
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
	if [[ "${FEDERATION_DOCTOR_SKIP_NETWORKS:-0}" == "1" ]]; then
		return 0
	fi
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

registry_publish_enabled() {
	local flag
	flag="$(env_value "${SITE_ENV}" FEDERATION_REGISTRY_PUBLISH_ENABLED)"
	case "${flag}" in
	true | 1 | yes | TRUE) printf 'true\n'; return 0 ;;
	esac
	if awk '/^\[registry\.publish\]/{found=1; next} /^\[/{found=0} found && /^enabled[[:space:]]*=[[:space:]]*true/{print "true"; exit}' \
		"${FEDERATION_TOML}" 2>/dev/null | grep -qx true; then
		printf 'true\n'
		return 0
	fi
	printf 'false\n'
}

toml_registry_signing_key_path() {
	awk '/^\[registry\.publish\]/{found=1; next} /^\[/{found=0} found && /^signing_key_path/{
		sub(/^[^=]+=[[:space:]]*"/, ""); sub(/".*$/, ""); print; exit
	}' "${FEDERATION_TOML}" 2>/dev/null
}

sync_container_name() {
	"${ENV_SELECTION}" sync_container
}

check_registry() {
	if [[ "${FEDERATION_DOCTOR_SKIP_REGISTRY:-0}" == "1" ]]; then
		return 0
	fi
	local fqdn sync_container publish_enabled signing_path host_path admin_token backend
	fqdn="$(toml_site_value fqdn)"
	[[ -n "${fqdn}" ]] || return 0
	sync_container="$(sync_container_name)"
	publish_enabled="$(registry_publish_enabled)"

	if [[ "${publish_enabled}" == "true" ]]; then
		signing_path="$(toml_registry_signing_key_path)"
		if [[ -z "${signing_path}" ]]; then
			signing_path="/etc/sds/secrets/registry/sign.pem"
		fi
		host_path="${FEDERATION_ROOT}/secrets/registry/sign.pem"
		if [[ ! -r "${host_path}" ]]; then
			record_fail "registry publish enabled but ${host_path} is not readable on the host"
		fi
		if docker ps --format '{{.Names}}' | grep -qx "${sync_container}"; then
			if ! docker exec "${sync_container}" test -r "${signing_path}" 2>/dev/null; then
				record_fail "signing key not readable in ${sync_container} at ${signing_path}"
			fi
		else
			info "Skipping in-container signing key check (${sync_container} not running)"
		fi
	fi

	if docker ps --format '{{.Names}}' | grep -qx "${sync_container}"; then
		if ! docker exec "${sync_container}" uv run python -c "
import sys, httpx
r = httpx.get('http://127.0.0.1:8000/.well-known/sds-federation.json', timeout=8)
sys.exit(0 if r.status_code == 200 else 1)
" 2>/dev/null; then
			record_fail "sync well-known /.well-known/sds-federation.json did not return 200 in ${sync_container}"
		fi
	else
		info "Skipping sync well-known probe (${sync_container} not running)"
	fi

	if [[ "${FEDERATION_DOCTOR_SKIP_DNS:-0}" != "1" && "${SDS_ENV_TYPE}" == "production" ]]; then
		local code
		code="$(curl -ksS -o /dev/null -w '%{http_code}' \
			"https://${fqdn}/internal/registry/capabilities" 2>/dev/null || printf '000')"
		if [[ "${code}" == "200" || "${code}" == "401" || "${code}" == "503" ]]; then
			record_fail "/internal/registry exposed on public hostname ${fqdn} (HTTP ${code})"
		fi
	fi

	local env_fp pub_path computed_fp
	env_fp="$(env_value "${SITE_ENV}" FEDERATION_REGISTRY_PUBKEY_FINGERPRINT)"
	if [[ -z "${env_fp}" ]]; then
		env_fp="$(env_value "${SHARED_ENV}" FEDERATION_REGISTRY_PUBKEY_FINGERPRINT)"
	fi
	pub_path="/etc/sds/certs/sds-registry.pub.pem"
	if [[ -n "${env_fp}" && -r "${FEDERATION_ROOT}/certs/sds-registry.pub.pem" ]]; then
		if docker ps --format '{{.Names}}' | grep -qx "${sync_container}"; then
			computed_fp="$(docker exec "${sync_container}" uv run sds-federation-registry fingerprint --public-key-path "${pub_path}" 2>/dev/null || true)"
			if [[ -n "${computed_fp}" && "${computed_fp}" != "${env_fp}" ]]; then
				record_fail "FEDERATION_REGISTRY_PUBKEY_FINGERPRINT mismatch (env ${env_fp} vs ${computed_fp})"
			fi
		fi
	fi

	if [[ "${publish_enabled}" == "true" ]]; then
		admin_token="$(env_value "${SHARED_ENV}" FEDERATION_SYNC_ADMIN_TOKEN)"
		if [[ -z "${admin_token}" ]]; then
			record_fail "registry publish enabled but FEDERATION_SYNC_ADMIN_TOKEN missing in federation-shared.env (sync internal API)"
		fi
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

traefik_conf_dir() {
	printf '%s\n' "${FEDERATION_DOCTOR_TRAEFIK_CONF_DIR:-${FEDERATION_ROOT}/../network/traefik/conf.d}"
}

check_traefik_routes() {
	if [[ "${FEDERATION_DOCTOR_SKIP_TRAEFIK:-0}" == "1" ]]; then
		return 0
	fi
	if [[ "${SDS_ENV_TYPE}" != "production" ]]; then
		info "Skipping Traefik route check (non-production)"
		return 0
	fi
	local fqdn conf_dir
	fqdn="$(toml_site_value fqdn)"
	[[ -n "${fqdn}" ]] || return 0
	conf_dir="$(traefik_conf_dir)"
	if [[ ! -d "${conf_dir}" ]]; then
		record_fail "Traefik conf.d missing at ${conf_dir}"
		return 0
	fi
	if ! traefik_sync_route_exists_for_fqdn "${fqdn}" "${conf_dir}"; then
		record_fail "Traefik missing Host(\`${fqdn}\`) && PathPrefix(\`/sync\`) in ${conf_dir}"
	fi
	if ! traefik_wellknown_route_exists_for_fqdn "${fqdn}" "${conf_dir}"; then
		record_fail "Traefik missing Host(\`${fqdn}\`) route for /.well-known/sds-federation.json in ${conf_dir}"
	fi
}

check_public_endpoints() {
	if [[ "${FEDERATION_DOCTOR_SKIP_PUBLIC:-0}" == "1" ]]; then
		return 0
	fi
	if [[ "${FEDERATION_DOCTOR_SKIP_DNS:-0}" == "1" ]]; then
		info "Skipping public endpoint check (FEDERATION_DOCTOR_SKIP_DNS=1)"
		return 0
	fi
	if [[ "${SDS_ENV_TYPE}" != "production" ]]; then
		info "Skipping public endpoint check (non-production)"
		return 0
	fi
	local fqdn expected body health status wk_fqdn
	fqdn="$(toml_site_value fqdn)"
	[[ -n "${fqdn}" ]] || return 0
	expected="$(normalize_fqdn "${fqdn}")"
	if ! command -v jq >/dev/null 2>&1; then
		record_fail "jq required for public endpoint check (install jq or set FEDERATION_DOCTOR_SKIP_PUBLIC=1)"
		return 0
	fi
	health="$(curl -ksS --max-time 20 "https://${fqdn}/sync/health" 2>/dev/null || true)"
	if [[ -z "${health}" ]] || ! jq -e '.status == "ok"' >/dev/null <<<"${health}"; then
		record_fail "https://${fqdn}/sync/health did not return status ok"
	fi
	body="$(curl -ksS --max-time 20 "https://${fqdn}/.well-known/sds-federation.json" 2>/dev/null || true)"
	if [[ -z "${body}" ]]; then
		record_fail "https://${fqdn}/.well-known/sds-federation.json returned empty response"
		return 0
	fi
	if ! jq -e 'type == "object"' >/dev/null <<<"${body}"; then
		record_fail "well-known JSON at https://${fqdn}/.well-known/sds-federation.json is not a JSON object"
		return 0
	fi
	wk_fqdn="$(jq -r '.fqdn // empty' <<<"${body}")"
	wk_fqdn="$(normalize_fqdn "${wk_fqdn}")"
	if [[ -z "${wk_fqdn}" ]]; then
		record_fail "well-known JSON missing fqdn field for https://${fqdn}/"
	elif [[ "${wk_fqdn}" != "${expected}" ]]; then
		record_fail "well-known fqdn (${wk_fqdn}) != site SDS_SITE_FQDN (${expected})"
	fi
}

challenge_env_file() {
	printf '%s\n' "${FEDERATION_DOCTOR_CHALLENGE_ENV:-${SITE_ENV}}"
}

fetch_well_known_json_for_challenge() {
	local fqdn=$1 body sync_container
	fqdn="$(normalize_fqdn "${fqdn}")"
	[[ -n "${fqdn}" ]] || return 1
	sync_container="$(sync_container_name)"
	if docker ps --format '{{.Names}}' | grep -qx "${sync_container}"; then
		body="$(docker exec "${sync_container}" uv run python -c "
import httpx
r = httpx.get('http://127.0.0.1:8000/.well-known/sds-federation.json', timeout=12)
r.raise_for_status()
print(r.text)
" 2>/dev/null || true)"
		if [[ -n "${body}" ]]; then
			printf '%s\n' "${body}"
			return 0
		fi
	fi
	if [[ "${FEDERATION_DOCTOR_SKIP_PUBLIC:-0}" == "1" ]] || [[ "${FEDERATION_DOCTOR_SKIP_DNS:-0}" == "1" ]]; then
		return 1
	fi
	body="$(curl -ksS --max-time 20 "https://${fqdn}/.well-known/sds-federation.json" 2>/dev/null || true)"
	if [[ -n "${body}" ]]; then
		printf '%s\n' "${body}"
		return 0
	fi
	return 1
}

check_registry_challenge() {
	local challenge_env token fqdn body require
	challenge_env="$(challenge_env_file)"
	require="${FEDERATION_DOCTOR_REQUIRE_CHALLENGE:-0}"
	token="$(env_value "${challenge_env}" FEDERATION_REGISTRY_CHALLENGE_TOKEN)"
	if [[ -z "${token}" ]]; then
		if [[ "${require}" == "1" ]]; then
			record_fail "FEDERATION_REGISTRY_CHALLENGE_TOKEN missing in ${challenge_env}"
		else
			info "Skipping registry challenge check (no token in ${challenge_env})"
		fi
		return 0
	fi
	fqdn="$(toml_site_value fqdn)"
	[[ -n "${fqdn}" ]] || {
		record_fail "federation.toml [site].fqdn missing (registry challenge check)"
		return 0
	}
	if ! body="$(fetch_well_known_json_for_challenge "${fqdn}")"; then
		record_fail "could not fetch well-known JSON for registry challenge check (${fqdn})"
		return 0
	fi
	if ! printf '%s' "${body}" | FEDERATION_CHALLENGE_TOKEN="${token}" uv run python -c "
import json, os, sys
from sds_federation.services.registry_challenge import challenge_matches, hash_registry_challenge_token

token = os.environ['FEDERATION_CHALLENGE_TOKEN']
doc = json.load(sys.stdin)
stored = hash_registry_challenge_token(token.strip())
sys.exit(0 if challenge_matches(doc, stored) else 1)
" 2>/dev/null; then
		record_fail "registry_challenge in well-known JSON does not match FEDERATION_REGISTRY_CHALLENGE_TOKEN"
	fi
}

check_registry_apply_ready() {
	local publish_enabled registry_url
	publish_enabled="$(registry_publish_enabled)"
	if [[ "${publish_enabled}" == "true" ]]; then
		info "registry publish enabled (flagship); skipping peer registry-apply checks"
		return 0
	fi
	registry_url="$(env_value "${SITE_ENV}" FEDERATION_REGISTRY_URL)"
	if [[ -z "${registry_url}" ]] && [[ -f "${FEDERATION_TOML}" ]]; then
		registry_url="$(awk '
/^\[registry\]/{found=1; next} /^\[/{found=0}
found && /^url[[:space:]]*=/{
	sub(/^[^=]+=[[:space:]]*"/,""); sub(/".*$/,""); print; exit
}' "${FEDERATION_TOML}" 2>/dev/null)"
	fi
	local pubkey_host="${FEDERATION_DOCTOR_REGISTRY_PUBKEY_HOST:-${FEDERATION_ROOT}/certs/sds-registry.pub.pem}"
	if [[ -n "${registry_url}" ]] && [[ ! -r "${pubkey_host}" ]]; then
		if [[ "${FEDERATION_REGISTRY_SKIP_PUBKEY_FETCH:-0}" != "1" ]]; then
			export FEDERATION_REGISTRY_URL="${registry_url}"
			"${FEDERATION_ROOT}/scripts/bin/fetch-registry-pubkey.sh" || true
		fi
	fi
	if [[ -n "${registry_url}" ]] && [[ ! -r "${pubkey_host}" ]]; then
		record_fail "FEDERATION_REGISTRY_URL is set but registry public key is missing on the host (${pubkey_host})"
	fi
}

run_preflight_apply() {
	local fqdn
	for c in identity token db_token networks dns ca sync_url traefik_routes registry_apply_ready public_endpoints registry_challenge registry; do
		run_check "${c}"
	done
	if ((FAILURES > 0)); then
		die "${FAILURES} preflight check(s) failed"
	fi
	fqdn="$(toml_site_value fqdn)"
	info "All preflight checks passed"
	if [[ -n "${fqdn}" ]]; then
		printf '\nRegistry application FQDN (use exactly): %s\n' "${fqdn}"
	fi
}

run_check() {
	local name=$1
	info "check_${name}"
	"check_${name}"
}

main() {
	local only=${1:-}
	require_file "${FEDERATION_TOML}"
	if [[ "${only}" == "preflight_apply" ]]; then
		run_preflight_apply
		return 0
	fi
	if [[ -n "${only}" ]]; then
		run_check "${only}"
	else
		for c in identity token db_token networks dns ca sync_url registry doc_site; do
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
