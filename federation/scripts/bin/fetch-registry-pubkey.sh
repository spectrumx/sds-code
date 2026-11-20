#!/usr/bin/env bash
# Download the mothership registry verifying public key into federation/certs/.
set -euo pipefail

# shellcheck source=../lib/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/common.sh"
# shellcheck source=lib/site_env.sh
source "${FEDERATION_ROOT}/scripts/lib/site_env.sh"

REGISTRY_PUBKEY_FILENAME="sds-registry.pub.pem"

registry_pubkey_dest() {
	printf '%s/certs/%s\n' "${FEDERATION_ROOT}" "${REGISTRY_PUBKEY_FILENAME}"
}

registry_pubkey_url() {
	local base=${1%/}
	printf '%s/%s\n' "${base}" "${REGISTRY_PUBKEY_FILENAME}"
}

fingerprint_from_site_env() {
	local file line raw
	file="$(site_env_path)"
	[[ -f "${file}" ]] || return 0
	line="$(grep -E '^FEDERATION_REGISTRY_PUBKEY_FINGERPRINT=' "${file}" 2>/dev/null | tail -1)" || return 0
	[[ -n "${line}" ]] || return 0
	raw="${line#*=}"
	if [[ "${raw}" == \"*\" && "${raw}" == *\" ]]; then
		raw="${raw:1:${#raw}-2}"
	fi
	printf '%s\n' "${raw}"
}

main() {
	local dest url tmp expected_fp computed
	dest="$(registry_pubkey_dest)"
	load_site_env_file 2>/dev/null || true
	local base="${FEDERATION_REGISTRY_URL:-}"
	[[ -n "${base}" ]] || die "FEDERATION_REGISTRY_URL is unset (set in site.env or export)"
	url="$(registry_pubkey_url "${base}")"
	if [[ -r "${dest}" && "${FEDERATION_REGISTRY_PUBKEY_FORCE_FETCH:-0}" != "1" ]]; then
		info "Registry public key already present at ${dest} (set FEDERATION_REGISTRY_PUBKEY_FORCE_FETCH=1 to re-download)"
		return 0
	fi
	mkdir -p "$(dirname "${dest}")"
	tmp="$(mktemp)"
	info "Fetching registry public key from ${url}"
	if ! curl -fsSL --max-time 45 "${url}" -o "${tmp}"; then
		rm -f "${tmp}"
		die "Failed to download registry public key from ${url}"
	fi
	if ! grep -q 'BEGIN PUBLIC KEY' "${tmp}"; then
		rm -f "${tmp}"
		die "Downloaded file from ${url} is not a PEM public key"
	fi
	mv "${tmp}" "${dest}"
	chmod 0644 "${dest}"
	expected_fp="$(fingerprint_from_site_env)"
	if [[ -z "${expected_fp}" ]]; then
		expected_fp="${FEDERATION_REGISTRY_PUBKEY_FINGERPRINT:-}"
	fi
	if [[ -n "${expected_fp}" ]]; then
		computed="$(cd "${FEDERATION_ROOT}" && uv run sds-federation-registry fingerprint --public-key-path "${dest}")"
		if [[ "${computed}" != "${expected_fp}" ]]; then
			rm -f "${dest}"
			die "Registry public key fingerprint mismatch (expected ${expected_fp}, got ${computed})"
		fi
		info "Public key fingerprint OK (${computed})"
	fi
	info "Wrote ${dest}"
}

main "$@"