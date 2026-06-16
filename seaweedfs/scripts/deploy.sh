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
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/s3-credentials.sh"

readonly DEFAULT_MAX_WAIT=60

function show_usage() {
	echo -e "Usage: ${0} [OPTIONS] <local|production|ci>"
	echo ""
	echo "Deploy the SeaweedFS stack: start services, configure S3 credentials, create bucket."
	echo ""
	echo -e "\e[34mOPTIONS:\e[0m"
	echo "    --auto-gen-prod-env Auto-generate production environment secrets"
	echo "                        Skips generation if file already exists."
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
	s3_configure_identity "$@"
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

function validate_production_credentials() {
	local env_type="$1"
	local access_key="$2"
	local secret_key="$3"

	if [[ "${env_type}" != "production" ]]; then
		log_msg "Skipping credential validation for '${env_type}' environment"
		return 0
	fi

	log_header "Validating Production Credentials"

	if [[ "${access_key}" == "admin-access-key" || "${access_key}" == "backup-access-key" ]]; then
		log_fatal_and_exit "Access key '${access_key}' is a well-known default. Set strong credentials in the env file."
	fi

	if [[ ${#access_key} -lt 16 ]]; then
		log_fatal_and_exit "Access key is too short (${#access_key} chars). Minimum 16 characters required for production."
	fi

	if [[ ${#secret_key} -lt 16 ]]; then
		log_fatal_and_exit "Secret key is too short (${#secret_key} chars). Minimum 16 characters required for production."
	fi

	log_success "Production credentials validated"
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
		--auto-gen-prod-env)
			_args_ref["auto_gen_prod_env"]="true"
			shift
			;;
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
		# File exists — ensure JWT keys are present
		local needs_update=false
		if ! grep -qE '^JWT_SIGNING_KEY=.+' "${ci_env_file}" 2>/dev/null; then
			echo "JWT_SIGNING_KEY=$(openssl rand -hex 16)" >>"${ci_env_file}"
			needs_update=true
		fi
		if ! grep -qE '^JWT_FILER_SIGNING_KEY=.+' "${ci_env_file}" 2>/dev/null; then
			echo "JWT_FILER_SIGNING_KEY=$(openssl rand -hex 16)" >>"${ci_env_file}"
			needs_update=true
		fi
		if ! grep -qE '^S3_SSE_KEK=.+' "${ci_env_file}" 2>/dev/null; then
			echo "S3_SSE_KEK=$(openssl rand -hex 16)" >>"${ci_env_file}"
			needs_update=true
		fi
		if [[ "${needs_update}" == "true" ]]; then
			log_success "Appended missing JWT keys to CI sfs.env"
		fi
		return 0
	fi

	log_msg "Generating CI sfs.env with JWT keys..."
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
JWT_SIGNING_KEY=$(openssl rand -hex 16)
JWT_FILER_SIGNING_KEY=$(openssl rand -hex 16)
S3_SSE_KEK=$(openssl rand -hex 16)
EOF
	chmod 600 "${ci_env_file}"
	log_success "CI sfs.env created with generated JWT keys"
}

function ensure_local_sfs_env() {
	local env_type="$1"
	if [[ "${env_type}" != "local" ]]; then
		return 0
	fi

	local local_env_file="${SFS_ROOT}/.envs/local/sfs.env"
	mkdir -p "$(dirname "${local_env_file}")"

	if [[ ! -f "${local_env_file}" ]]; then
		log_msg "Generating local sfs.env with JWT keys..."
		cat >"${local_env_file}" <<EOF
# Auto-generated JWT keys for local development
JWT_SIGNING_KEY=$(openssl rand -hex 16)
JWT_FILER_SIGNING_KEY=$(openssl rand -hex 16)
S3_SSE_KEK=$(openssl rand -hex 16)
EOF
		chmod 600 "${local_env_file}"
		log_success "Local sfs.env created with generated JWT keys"
		return 0
	fi

	# File exists — check if JWT keys are set, append if missing
	local needs_update=false
	if ! grep -qE '^JWT_SIGNING_KEY=.+' "${local_env_file}" 2>/dev/null; then
		echo "JWT_SIGNING_KEY=$(openssl rand -hex 16)" >>"${local_env_file}"
		needs_update=true
	fi
	if ! grep -qE '^JWT_FILER_SIGNING_KEY=.+' "${local_env_file}" 2>/dev/null; then
		echo "JWT_FILER_SIGNING_KEY=$(openssl rand -hex 16)" >>"${local_env_file}"
		needs_update=true
	fi
	if ! grep -qE '^S3_SSE_KEK=.+' "${local_env_file}" 2>/dev/null; then
		echo "S3_SSE_KEK=$(openssl rand -hex 16)" >>"${local_env_file}"
		needs_update=true
	fi

	if [[ "${needs_update}" == "true" ]]; then
		log_success "Appended missing JWT keys to local sfs.env"
	fi
}

function validate_required_secrets() {
	local env_type="$1"
	local env_file

	case "${env_type}" in
	local) env_file="${SFS_ROOT}/.envs/local/sfs.env" ;;
	ci) env_file="${SFS_ROOT}/.envs/ci/sfs.env" ;;
	production) env_file="${SFS_ROOT}/.envs/production/sfs.env" ;;
	*)
		log_error "Unknown environment: ${env_type}"
		return 1
		;;
	esac

	if [[ ! -f "${env_file}" ]]; then
		log_error "Environment file not found: ${env_file}"
		log_msg "Run deploy.sh to generate it automatically (local/CI) or create it manually (production)."
		return 1
	fi

	local missing=()
	if ! grep -qE '^JWT_SIGNING_KEY=.+' "${env_file}" 2>/dev/null; then
		missing+=("JWT_SIGNING_KEY")
	fi
	if ! grep -qE '^JWT_FILER_SIGNING_KEY=.+' "${env_file}" 2>/dev/null; then
		missing+=("JWT_FILER_SIGNING_KEY")
	fi
	if ! grep -qE '^S3_SSE_KEK=.+' "${env_file}" 2>/dev/null; then
		missing+=("S3_SSE_KEK")
	fi

	if [[ ${#missing[@]} -gt 0 ]]; then
		log_error "Required JWT secrets missing or empty in ${env_file}:"
		for secret in "${missing[@]}"; do
			log_msg "  - ${secret}"
		done
		log_msg "Generate them with: openssl rand -hex 16 for each missing key."
		if [[ "${env_type}" == "production" ]]; then
			log_msg "For production, set these via secure secret injection before deploying."
		fi
		return 1
	fi

	log_success "All required JWT secrets are set in ${env_file}"
}

function generate_production_env() {
	local env_type="$1"
	local auto_gen_prod_env="$2"

	if [[ "${env_type}" == "production" && "${auto_gen_prod_env}" == "true" ]]; then
		log_header "Production Environment Generation"
		echo -e "\n\e[31mWARNING: This should only be done for a new empty deployment. Generating a new environment may result in loss of access to existing data.\e[0m"
		printf "Are you sure you want to proceed? [y/N] "
		read -r response
		if [[ "${response}" != "y" ]]; then
			log_fatal_and_exit "Auto-generation aborted by user."
		fi

		local prod_env_file="${SFS_ROOT}/.envs/production/sfs.env"
		if [ -f "${prod_env_file}" ]; then
			log_error_and_skip "env file already exists; not overwriting it: '${prod_env_file}'"
			return 0
		fi
		mkdir -p "$(dirname "${prod_env_file}")"
		log_msg "Generating ${prod_env_file}..."
		cat >"${prod_env_file}" <<EOF
JWT_SIGNING_KEY=$(openssl rand -hex 16)
JWT_FILER_SIGNING_KEY=$(openssl rand -hex 16)
S3_SSE_KEK=$(openssl rand -hex 16)
EOF
		chmod 600 "${prod_env_file}"
		log_success "Production environment file generated."

		log_msg "Creating immediate snapshot of new secrets..."
		bash "${SFS_ROOT}/../gateway/scripts/create-snapshot.sh" production
	fi
}

function main() {
	declare -A args=(
		[env_type]=""
		[skip_setup]="false"
		[sfs_env]=""
		[auto_gen_prod_env]="false"
	)

	parse_arguments args "$@"

	cd "${SFS_ROOT}"
	log_header "SeaweedFS Deployment - ${args[env_type]} environment"

	generate_production_env "${args[env_type]}" "${args[auto_gen_prod_env]}"
	assert_selected_env "${args[env_type]}"
	ensure_ci_sfs_env
	ensure_local_sfs_env "${args[env_type]}"
	validate_required_secrets "${args[env_type]}"
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

		validate_production_credentials "${args[env_type]}" "${access_key}" "${secret_key}"
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
			validate_production_credentials "${args[env_type]}" "${sec_access_key}" "${sec_secret_key}"
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
