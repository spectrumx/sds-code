#!/usr/bin/env bash
# Deploy the SeaweedFS stack: start services, configure S3 credentials, create bucket.
#
# By default, S3 credentials are read from .envs/<env>/storage.env (PRIMARY vars).
# Pass --sfs-env to override the credentials file path (used by gateway/deploy.sh).
#
# ENVIRONMENT VARIABLES:
#   SFS_FORCE_SECRETS  - Set to 'true' to overwrite existing .envs files (default: false)
#   SFS_SKIP_SETUP     - Set to 'true' to skip credential/bucket setup (default: false)
#
# USAGE EXAMPLES:
#   ./deploy.sh local
#   ./deploy.sh ci
#   ./deploy.sh production
#   ./deploy.sh --sfs-env /path/to/storage.env local

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SFS_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/common.sh"

readonly DEFAULT_MAX_WAIT=60

function show_usage() {
	echo -e "Usage: ${0} [OPTIONS] <local|production|ci>"
	echo ""
	echo "Deploy the SeaweedFS stack: start services, configure S3 credentials, create bucket."
	echo ""
	echo -e "\e[34mOPTIONS:\e[0m"
	echo "    --sfs-env <file>    Path to env file with S3 credentials"
	echo "                        (defaults to .envs/<env>/storage.env)"
	echo "    --skip-setup        Skip credential and bucket setup"
	echo "    -h, --help          Show this help message"
	echo ""
	echo -e "\e[34mARGUMENTS:\e[0m"
	echo "    <local|production|ci>   Target environment to deploy"
	echo ""
	echo -e "\e[34mCREDENTIALS FILE FORMAT:\e[0m"
	echo "    PRIMARY_ACCESS_KEY_ID=<key>"
	echo "    PRIMARY_SECRET_ACCESS_KEY=<secret>"
	echo "    PRIMARY_STORAGE_BUCKET_NAME=<bucket>"
	echo ""
	echo -e "\e[34mEXAMPLES:\e[0m"
	echo "    ${0} local"
	echo "    ${0} ci"
	echo "    ${0} --sfs-env .envs/production/storage.env production"
	echo ""
	exit 0
}

# Return 0 if running as root, 1 otherwise
function is_root() {
	[[ $(id -u) -eq 0 ]]
}

function setup_data_dirs() {
	local env_type="$1"
	if [[ "${env_type}" != "local" ]]; then
		return 0
	fi

	log_header "Local Data Directory Setup"
	log_msg "Creating data directories..."
	local uid gid
	uid=$(id -u)
	gid=$(id -g)
	# Export for compose (UID/GID are readonly in bash, so we use HOST_UID/HOST_GID)
	export HOST_UID="${uid}" HOST_GID="${gid}"
	mkdir -p "${SFS_ROOT}/data/volumes" "${SFS_ROOT}/data/filer/filerldb2"
	# Dirs created by current user → already owned by ${uid}:${gid}
	# Container also runs as ${uid}:${gid} via compose user: ${HOST_UID}:${HOST_GID}
	# → no chown needed.

	log_success "Data directories ready (uid=${uid}, gid=${gid})"
}

function start_stack() {
	log_header "Starting SFS stack"
	log_msg "Starting stack..."
	{
		just build
		just up
	} &>/dev/null &
}

function env_prefix() {
	if [[ "$1" == "production" ]]; then
		echo "prod"
	else
		echo "$1"
	fi
}

function wait_for_s3_health() {
	local env_type="$1"
	local max_attempts="${2:-${DEFAULT_MAX_WAIT}}"
	local prefix
	prefix=$(env_prefix "${env_type}")
	local s3_container="sds-gateway-${prefix}-sfs-s3"
	local s3_port="${SFS_S3_PORT:-8333}"

	log_msg "Waiting for S3 gateway to be healthy (container: ${s3_container})..."

	local attempt=1
	while [[ ${attempt} -le ${max_attempts} ]]; do
		if docker exec "${s3_container}" curl -fsS "http://localhost:${s3_port}/healthz" >/dev/null 2>&1; then
			log_success "S3 gateway is healthy"
			return 0
		fi

		if [[ $((attempt % 10)) -eq 0 ]]; then
			log_msg "Still waiting... (attempt ${attempt}/${max_attempts})"
			log_msg "=== S3 gateway logs (last 20 lines) ==="
			docker logs --tail 20 "${s3_container}" 2>&1 | while IFS= read -r line; do
				log_msg "  ${line}"
			done
			log_msg "========================================="
		fi

		sleep 2
		attempt=$((attempt + 1))
	done

	log_error "S3 gateway '${s3_container}' did not become healthy in time"
	return 1
}

function configure_s3_credentials() {
	local env_type="$1"
	local access_key="$2"
	local secret_key="$3"
	local prefix
	prefix=$(env_prefix "${env_type}")
	local filer_container="sds-gateway-${prefix}-sfs-filer"
	local master_container="sds-gateway-${prefix}-sfs-master"

	log_header "Configuring S3 Credentials"
	log_msg "Configuring S3 identity '${access_key}' on cluster..."

	printf '%s\n' "s3.configure -apply -user ${access_key} -access_key ${access_key} -secret_key ${secret_key} -actions Admin -buckets *" |
		docker exec -i "${filer_container}" weed shell \
			-master="${master_container}:9333"

	log_success "S3 credentials configured"
}

function create_bucket() {
	local env_type="$1"
	local bucket_name="$2"
	local access_key="$3"
	local secret_key="$4"
	local prefix
	prefix=$(env_prefix "${env_type}")
	local filer_container="sds-gateway-${prefix}-sfs-filer"
	local master_container="sds-gateway-${prefix}-sfs-master"

	log_header "Creating S3 Bucket"
	log_msg "Creating bucket '${bucket_name}'..."

	printf '%s\n' "s3.bucket.create -name ${bucket_name}" |
		docker exec -i "${filer_container}" weed shell \
			-master="${master_container}:9333"

	log_success "Bucket '${bucket_name}' ready"
}

function setup_prod_hostnames() {
	local env_type="$1"
	local example_file="${SCRIPT_DIR}/prod-hostnames.example.env"
	local target_file="${SCRIPT_DIR}/prod-hostnames.env"

	if [[ -f "${example_file}" && ! -f "${target_file}" ]]; then
		cp "${example_file}" "${target_file}"
		log_msg "Created: ${target_file}"
	fi

	if [[ "${env_type}" == "production" && -f "${target_file}" ]]; then
		local current_hostname
		current_hostname=$(hostname)
		local rel_path
		rel_path=$(realpath --relative-to="." "${target_file}")

		if [[ -n "${current_hostname}" ]]; then
			if ! grep -Fxq "${current_hostname}" "${target_file}"; then
				log_error "Current hostname '${current_hostname}' not listed in '${rel_path}'."
				log_msg "Add it:\n\n\techo '${current_hostname}' >> ${rel_path}"
				exit 1
			fi
		fi
	fi
}

function load_credentials() {
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

function load_secondary_credentials() {
	local env_file="$1"

	if [[ ! -f "${env_file}" ]]; then
		return 1
	fi

	local access_key secret_key
	access_key=$(grep -E '^SECONDARY_ACCESS_KEY_ID=' "${env_file}" | cut -d'=' -f2-)
	secret_key=$(grep -E '^SECONDARY_SECRET_ACCESS_KEY=' "${env_file}" | cut -d'=' -f2-)

	# If neither SECONDARY credential is set, the store is not configured
	if [[ -z "${access_key}" || -z "${secret_key}" ]]; then
		return 1
	fi

	# Filter out placeholder/admin defaults that indicate unset creds
	if [[ "${access_key}" == "admin" && "${secret_key}" == "admin" ]]; then
		return 1
	fi

	printf '%s\n%s' "${access_key}" "${secret_key}"
}

function parse_arguments() {
	local -n _args_ref=$1
	shift

	# Ensure key exists (shellcheck can't follow nameref)
	if [[ -z "${_args_ref["skip_setup"]+x}" ]]; then
		_args_ref["skip_setup"]="false"
	fi
	if [[ -z "${_args_ref["sfs_env"]+x}" ]]; then
		_args_ref["sfs_env"]=""
	fi
	if [[ "${SFS_SKIP_SETUP:-}" == "true" ]]; then
		_args_ref["skip_setup"]="true"
	fi

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
		--skip-setup)
			_args_ref["skip_setup"]="true"
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

function assert_selected_env() {
	local env_type="$1"
	log_msg "assert_selected_env: checking env_type='${env_type}'"

	# Directly use env-selection.sh to detect what environment it resolves to
	# (without calling 'just env' which fails if .envs/ci/sfs.env is missing).
	local selected_env
	selected_env="$(cd "${SFS_ROOT}" && bash "${SCRIPT_DIR}/env-selection.sh" env)"
	log_msg "assert_selected_env: detected env='${selected_env}' (requested='${env_type}')"

	# If they match, we're good. If not, explain why.
	if [[ "${env_type}" != "${selected_env}" ]]; then
		# Show what env-selection.sh detected and why
		log_msg "assert_selected_env: env mismatch!"
		log_msg "  SDS_ENV=${SDS_ENV:-<not set>}"
		log_msg "  CI=${CI:-<not set>}"
		log_msg "  GITHUB_ACTIONS=${GITHUB_ACTIONS:-<not set>}"
		log_msg "  GITLAB_CI=${GITLAB_CI:-<not set>}"
		log_msg "  BUILD_ID=${BUILD_ID:-<not set>}"
		log_msg "  JENKINS_URL=${JENKINS_URL:-<not set>}"
		log_msg "  Hostname: $(hostname)"
		if [[ -f "${SCRIPT_DIR}/prod-hostnames.env" ]]; then
			log_msg "  prod-hostnames.env exists ($(wc -l <"${SCRIPT_DIR}/prod-hostnames.env") lines)"
		else
			log_warning "  prod-hostnames.env NOT FOUND at '${SCRIPT_DIR}/prod-hostnames.env'"
		fi

		# Check if just env recipe would fail too
		log_msg "Checking just env recipe for diagnostics:"
		local compose_file env_file
		compose_file="$(cd "${SFS_ROOT}" && bash "${SCRIPT_DIR}/env-selection.sh" compose_file)"
		env_file="$(cd "${SFS_ROOT}" && bash "${SCRIPT_DIR}/env-selection.sh" env_file)"
		log_msg "  compose_file='${compose_file}' exists=${compose_file:+"$(test -f "${SFS_ROOT}/${compose_file}" && echo yes || echo no)"}"
		log_msg "  env_file='${env_file}' exists=${env_file:+"$(test -f "${SFS_ROOT}/${env_file}" && echo yes || echo no)"}"

		log_error "Requested env '${env_type}' does not match detected env '${selected_env}'"
		log_msg "If running locally with CI env, set SDS_ENV=${env_type} or export CI=1 before running this script."
		log_msg "  e.g.: SDS_ENV=${env_type} ${0} ${env_type}"
		log_msg "  e.g.: CI=1 ${0} ${env_type}"
		exit 1
	fi

	log_success "assert_selected_env: env '${env_type}' OK"
}

function ensure_ci_sfs_env() {
	# CI sfs.env is git-ignored; generate a minimal one if missing.
	# Only needed for 'just env' recipe — compose.ci.yaml ports have
	# defaults, so values here only matter for 'just env' output.
	local ci_env_file="${SFS_ROOT}/.envs/ci/sfs.env"

	if [[ -f "${ci_env_file}" ]]; then
		return 0
	fi

	log_msg "Generating minimal CI sfs.env (git-ignored, safe for ephemeral CI)..."
	local uid gid
	uid=$(id -u)
	gid=$(id -g)

	# Create parent directory if it doesn't exist (git-ignored, may not be checked in)
	mkdir -p "$(dirname "${ci_env_file}")"

	cat >"${ci_env_file}" <<EOF
UID=${uid}
GID=${gid}
SFS_MASTER_PORT=9333
SFS_MASTER_GRPC_PORT=19333
SFS_MASTER_METRICS_PORT=9324
SFS_VOLUME_PORT=8080
SFS_VOLUME_GRPC_PORT=18080
SFS_VOLUME_METRICS_PORT=9325
SFS_FILER_PORT=8888
SFS_FILER_GRPC_PORT=18888
SFS_FILER_METRICS_PORT=9326
SFS_S3_PORT=8333
SFS_S3_METRICS_PORT=9327
SFS_WEBDAV_PORT=7333
SFS_PROMETHEUS_HOST_PORT=9000
SFS_PROMETHEUS_CONTAINER_PORT=9090
EOF
	chmod 600 "${ci_env_file}"
}

function main() {
	declare -A args=(
		[env_type]=""
		[skip_setup]="false"
		[sfs_env]=""
	)

	parse_arguments args "$@"

	cd "${SFS_ROOT}"
	log_header "SeaweedFS Deployment - ${args[env_type]} environment"

	assert_selected_env "${args[env_type]}"
	ensure_ci_sfs_env
	setup_prod_hostnames "${args[env_type]}"
	setup_data_dirs "${args[env_type]}"
	start_stack "${args[env_type]}"
	wait_for_s3_health "${args[env_type]}" "${DEFAULT_MAX_WAIT}"

	if [[ "${args[skip_setup]}" == "false" ]]; then
		local creds
		local sfs_env_path="${args[sfs_env]}"
		creds=$(just load_credentials "${sfs_env_path}")
		local access_key secret_key bucket_name
		access_key=$(echo "${creds}" | sed -n '1p')
		secret_key=$(echo "${creds}" | sed -n '2p')
		bucket_name=$(echo "${creds}" | sed -n '3p')

		configure_s3_credentials "${args[env_type]}" "${access_key}" "${secret_key}"
		create_bucket "${args[env_type]}" "${bucket_name}" "${access_key}" "${secret_key}"

		# Also configure SECONDARY S3 identity if credentials are available (local/dev)
		local secondary_creds
		secondary_creds=$(just load_secondary_credentials "${sfs_env_path}") || true
		if [[ -n "${secondary_creds}" ]]; then
			local sec_access_key sec_secret_key
			sec_access_key=$(echo "${secondary_creds}" | sed -n '1p')
			sec_secret_key=$(echo "${secondary_creds}" | sed -n '2p')
			log_msg "Configuring SECONDARY S3 identity on SeaweedFS..."
			configure_s3_credentials "${args[env_type]}" "${sec_access_key}" "${sec_secret_key}"
			log_success "SECONDARY S3 identity configured on SeaweedFS"
		fi
	else
		log_msg "Skipping credential and bucket setup (--skip-setup)"
	fi

	log_header "SeaweedFS deployment complete"
	log_msg "S3 endpoint: http://localhost:${SFS_S3_PORT:-8333}"
	log_msg "File browser: http://localhost:${SFS_FILER_PORT:-8888}"
}

main "$@"
