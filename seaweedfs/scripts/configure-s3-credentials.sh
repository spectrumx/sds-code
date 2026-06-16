#!/usr/bin/env bash
# Re-apply SeaweedFS S3 credentials from gateway storage.env and refresh mc alias.
#
# USAGE:
#   ./configure-s3-credentials.sh [OPTIONS] <local|production|ci>
#   ./configure-s3-credentials.sh --sfs-env ../gateway/.envs/production/storage.env production
#
# OPTIONS:
#   --sfs-env <file>   Path to gateway storage.env (default: ../gateway/.envs/<env>/storage.env)
#   --port <port>      Host port for mc alias (default: SFS_S3_PORT from sfs.env, else 8333)
#   --skip-mc          Skip mc alias configuration
#   -h, --help         Show help

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SFS_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/common.sh"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/s3-credentials.sh"

function show_usage() {
	echo -e "Usage: ${0} [OPTIONS] <local|production|ci>"
	echo ""
	echo "Re-apply S3 credentials from gateway storage.env to the running SeaweedFS cluster."
	echo ""
	echo -e "\e[34mOPTIONS:\e[0m"
	echo "    --sfs-env <file>   Path to env file with PRIMARY_* credentials"
	echo "    --port <port>      Host port for mc alias (default: SFS_S3_PORT or 8333)"
	echo "    --skip-mc          Skip mc alias configuration"
	echo "    -h, --help         Show this help message"
	echo ""
	exit 0
}

function load_storage_credentials() {
	local env_file="$1"

	if [[ ! -f "${env_file}" ]]; then
		log_error "Credentials file not found: ${env_file}"
		return 1
	fi

	local access_key secret_key bucket_name
	access_key=$(grep -E '^PRIMARY_ACCESS_KEY_ID=' "${env_file}" | cut -d'=' -f2-)
	secret_key=$(grep -E '^PRIMARY_SECRET_ACCESS_KEY=' "${env_file}" | cut -d'=' -f2-)
	bucket_name=$(grep -E '^PRIMARY_STORAGE_BUCKET_NAME=' "${env_file}" | cut -d'=' -f2-)

	if [[ -z "${access_key}" || -z "${secret_key}" || -z "${bucket_name}" ]]; then
		log_error "Missing required credentials in ${env_file}"
		log_msg "Expected: PRIMARY_ACCESS_KEY_ID, PRIMARY_SECRET_ACCESS_KEY, PRIMARY_STORAGE_BUCKET_NAME"
		return 1
	fi

	printf '%s\n%s\n%s' "${access_key}" "${secret_key}" "${bucket_name}"
}

function validate_production_credentials() {
	local env_type="$1"
	local access_key="$2"
	local secret_key="$3"

	if [[ "${env_type}" != "production" ]]; then
		return 0
	fi

	log_header "Validating Production Credentials"

	if [[ "${access_key}" == "admin-access-key" || "${access_key}" == "backup-access-key" ]]; then
		log_fatal_and_exit "Access key '${access_key}' is a well-known default. Set strong credentials in the env file."
	fi

	if [[ ${#access_key} -lt 4 ]]; then
		log_fatal_and_exit "Access key ID is too short (${#access_key} chars). Minimum 4 characters required for production."
	fi

	if [[ ${#secret_key} -lt 16 ]]; then
		log_fatal_and_exit "Secret key is too short (${#secret_key} chars). Minimum 16 characters required for production."
	fi

	log_success "Production credentials validated"
}

function parse_arguments() {
	local -n _args_ref=$1
	shift

	while [[ $# -gt 0 ]]; do
		case "$1" in
		--sfs-env)
			if [[ -z "${2:-}" ]]; then
				log_error "Missing value for --sfs-env"
				show_usage
			fi
			_args_ref["sfs_env"]="$2"
			shift 2
			;;
		--port)
			if [[ -z "${2:-}" ]]; then
				log_error "Missing value for --port"
				show_usage
			fi
			_args_ref["port"]="$2"
			shift 2
			;;
		--skip-mc)
			_args_ref["skip_mc"]="true"
			shift
			;;
		-h | --help)
			show_usage
			;;
		local | production | ci)
			_args_ref["env_type"]="$1"
			shift
			;;
		*)
			log_error "Unknown argument: $1"
			show_usage
			;;
		esac
	done

	if [[ -z "${_args_ref["env_type"]}" ]]; then
		log_error "Environment type required (local, production, or ci)"
		show_usage
	fi
}

function main() {
	declare -A args=(
		[env_type]=""
		[sfs_env]=""
		[port]=""
		[skip_mc]="false"
	)

	parse_arguments args "$@"

	cd "${SFS_ROOT}"

	local sfs_env_path="${args[sfs_env]:-${SFS_ROOT}/../gateway/.envs/${args[env_type]}/storage.env}"
	sfs_env_path=$(realpath "${sfs_env_path}")

	log_header "Reload S3 Credentials - ${args[env_type]} environment"
	log_msg "Reading credentials from ${sfs_env_path}"

	local creds access_key secret_key bucket_name host_port
	creds=$(load_storage_credentials "${sfs_env_path}")
	access_key=$(echo "${creds}" | sed -n '1p')
	secret_key=$(echo "${creds}" | sed -n '2p')
	bucket_name=$(echo "${creds}" | sed -n '3p')

	validate_production_credentials "${args[env_type]}" "${access_key}" "${secret_key}"
	s3_configure_identity "${args[env_type]}" "${access_key}" "${secret_key}"

	if [[ "${args[skip_mc]}" == "false" ]]; then
		host_port=$(s3_resolve_host_port "${args[env_type]}" "${args[port]}" "${SFS_ROOT}")
		s3_configure_mc_alias "${host_port}" "${access_key}" "${secret_key}"
	fi

	log_success "S3 credentials reloaded for bucket '${bucket_name}'"
}

main "$@"
