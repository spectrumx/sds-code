#!/usr/bin/env bash
# Map federation/certs (host) ↔ /etc/sds/certs (sync container). Requires FEDERATION_ROOT.
FEDERATION_CERTS_CONTAINER_DIR="/etc/sds/certs"

federation_certs_host_dir() {
	printf '%s/certs\n' "${FEDERATION_ROOT}"
}

_absolute_path() {
	local path=$1 dir base
	dir="$(cd "$(dirname "${path}")" && pwd)"
	base="$(basename "${path}")"
	printf '%s/%s' "${dir}" "${base}"
}

# Host path to check on the machine (from toml container path or operator input).
ca_cert_host_path_for_check() {
	local configured=$1
	local host_dir rel
	host_dir="$(federation_certs_host_dir)"
	if [[ "${configured}" == "${FEDERATION_CERTS_CONTAINER_DIR}/"* ]]; then
		rel="${configured#${FEDERATION_CERTS_CONTAINER_DIR}/}"
		printf '%s/%s\n' "${host_dir}" "${rel}"
		return 0
	fi
	if [[ "${configured}" == "${host_dir}/"* ]]; then
		printf '%s\n' "${configured}"
		return 0
	fi
	if [[ "${configured}" != /* ]]; then
		printf '%s/%s\n' "${host_dir}" "${configured}"
		return 0
	fi
	printf '%s\n' "${configured}"
}

# Normalize operator input to the container path written in federation.toml.
ca_cert_container_path_from_input() {
	local input=$1
	local host_dir host_path abs_host abs_certs rel
	[[ -n "${input}" ]] || die "ca_cert_path input empty"
	host_dir="$(federation_certs_host_dir)"
	if [[ "${input}" == "${FEDERATION_CERTS_CONTAINER_DIR}/"* ]]; then
		host_path="${host_dir}/${input#${FEDERATION_CERTS_CONTAINER_DIR}/}"
	elif [[ "${input}" != /* ]]; then
		host_path="${host_dir}/${input}"
	else
		host_path="${input}"
	fi
	[[ -e "${host_path}" ]] || die "CA cert not found: ${host_path}"
	abs_host="$(_absolute_path "${host_path}")"
	abs_certs="$(_absolute_path "${host_dir}")"
	case "${abs_host}" in
	"${abs_certs}"/*)
		rel="${abs_host#${abs_certs}/}"
		printf '%s/%s\n' "${FEDERATION_CERTS_CONTAINER_DIR}" "${rel}"
		;;
	*)
		die "CA cert must live under ${host_dir} (mounted in sync at ${FEDERATION_CERTS_CONTAINER_DIR})"
		;;
	esac
}
