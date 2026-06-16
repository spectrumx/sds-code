#!/usr/bin/env bash
# Shared helpers for applying SeaweedFS S3 identities from gateway storage.env.
# Source this file; do not execute directly.

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
	echo "This script must be sourced. Use: source ${BASH_SOURCE[0]}" >&2
	exit 1
fi

function s3_env_prefix() {
	if [[ "$1" == "production" ]]; then
		echo "prod"
	else
		echo "$1"
	fi
}

function s3_resolve_host_port() {
	local env_type="$1"
	local port_override="${2:-}"
	local sfs_root="${3:-}"

	if [[ -n "${port_override}" ]]; then
		printf '%s' "${port_override}"
		return 0
	fi

	local env_file=""
	case "${env_type}" in
	local) env_file="${sfs_root}/.envs/local/sfs.env" ;;
	ci) env_file="${sfs_root}/.envs/ci/sfs.env" ;;
	production) env_file="${sfs_root}/.envs/production/sfs.env" ;;
	esac

	if [[ -f "${env_file}" ]]; then
		local port
		port=$(grep -E '^SFS_S3_PORT=' "${env_file}" | cut -d'=' -f2- || true)
		if [[ -n "${port}" ]]; then
			printf '%s' "${port}"
			return 0
		fi
	fi

	printf '%s' "${SFS_S3_PORT:-8333}"
}

function s3_configure_identity() {
	local env_type="$1"
	local access_key="$2"
	local secret_key="$3"
	local prefix
	prefix=$(s3_env_prefix "${env_type}")
	local filer_container="sds-gateway-${prefix}-sfs-filer"
	local master_container="sds-gateway-${prefix}-sfs-master"

	log_header "Configuring S3 Credentials"
	log_msg "Configuring S3 identity '${access_key}' on cluster..."

	printf '%s\n' "s3.configure -apply -user ${access_key} -access_key ${access_key} -secret_key ${secret_key} -actions Admin -buckets *" |
		docker exec -i "${filer_container}" weed shell \
			-master="${master_container}:9333"

	log_success "S3 credentials configured"
}

function s3_configure_mc_alias() {
	local host_port="$1"
	local access_key="$2"
	local secret_key="$3"
	local alias_name="${4:-sfs}"

	if ! command -v mc >/dev/null 2>&1; then
		log_warning "mc not found on PATH; skipping 'mc alias set ${alias_name}'"
		return 0
	fi

	log_msg "Setting mc alias '${alias_name}' -> http://localhost:${host_port}"
	mc alias set "${alias_name}" "http://localhost:${host_port}" "${access_key}" "${secret_key}"
	log_success "mc alias '${alias_name}' configured"
}
