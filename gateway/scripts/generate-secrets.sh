#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
GATEWAY_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
SDS_ROOT=$(cd "${GATEWAY_ROOT}/.." && pwd)
FEDERATION_ROOT=""
if [[ -d "${SDS_ROOT}/federation" ]]; then
	FEDERATION_ROOT=$(cd "${SDS_ROOT}/federation" && pwd)
fi
SFS_ROOT=$(cd "${SDS_ROOT}/seaweedfs" && pwd)
EXAMPLE_DIR="${GATEWAY_ROOT}/.envs/example"
FEDERATION_SHARED_TEMPLATE="${SDS_ROOT}/federation-shared.example.env"
FEDERATION_SHARED_OUTPUT="${SDS_ROOT}/federation-shared.env"

# PRIMARY (RustFS or SeaweedFS)
PRIMARY_ACCESS_KEY_ID=""
PRIMARY_SECRET_ACCESS_KEY=""
PRIMARY_ENDPOINT_URL=""
PRIMARY_S3_ENDPOINT_URL=""

# SECONDARY (RustFS or SeaweedFS) — only for production
SECONDARY_ACCESS_KEY_ID=""
SECONDARY_SECRET_ACCESS_KEY=""

FEDERATION_SYNC_DRF_TOKEN=""

function ensure_federation_sync_drf_token() {
	local env_type="$1"
	if [[ -n "${FEDERATION_SYNC_DRF_TOKEN}" ]]; then
		return 0
	fi
	if [[ "${env_type}" == "ci" ]]; then
		FEDERATION_SYNC_DRF_TOKEN="ci-federation-sync-drf-01234567890123456"
	else
		FEDERATION_SYNC_DRF_TOKEN=$(generate_secret 40)
	fi
}

function usage() {
	cat <<EOF
Usage: ${0} [OPTIONS] <local|production|ci>

Generate environment secrets for the gateway component.

OPTIONS:
    -f, --force         Overwrite existing env files without prompting
    -h, --help          Show this help message

ARGUMENTS:
    <local|production|ci>   Target environment to generate secrets for

EXAMPLES:
    ${0} local              # Generate local env files (skip if they exist)
    ${0} --force ci         # Generate CI env files (overwrite if exist)
    ${0} production         # Generate production env files

    NOTES:
        - Generated gateway files are placed in gateway/.envs/<env>/
        - federation-shared.env is written to the repo root (from federation-shared.example.env)
        - Example templates are read from .envs/example/
        - Secrets are randomly generated using OpenSSL
        - CI environment uses insecure but deterministic values for ephemeral usage
        - local: PRIMARY (RustFS) + SECONDARY (SeaweedFS)
        - production: PRIMARY (SeaweedFS) + SECONDARY (RustFS)
        - ci: PRIMARY only (RustFS). No secondary storage.
EOF
	exit 0
}

function configure_object_store_defaults() {
	local env_type="$1"

	if [[ -n "${PRIMARY_ENDPOINT_URL}" ]]; then
		return 0
	fi

	case "${env_type}" in
	local)
		PRIMARY_ENDPOINT_URL="sds-gateway-local-rustfs:9000"
		PRIMARY_ACCESS_KEY_ID=$(generate_secret 32)
		PRIMARY_SECRET_ACCESS_KEY=$(generate_secret 32)
		# SECONDARY = SeaweedFS (S3 gateway)
		SECONDARY_ENDPOINT_URL="sds-gateway-local-sfs-s3:8333"
		SECONDARY_ACCESS_KEY_ID=$(generate_secret 32)
		SECONDARY_SECRET_ACCESS_KEY=$(generate_secret 32)
		;;
	ci)
		PRIMARY_ENDPOINT_URL="sds-gateway-ci-rustfs:9000"
		;;
	production)
		PRIMARY_ENDPOINT_URL="sds-gateway-prod-sfs-s3:8333"
		PRIMARY_ACCESS_KEY_ID="sfsadmin"
		PRIMARY_SECRET_ACCESS_KEY=$(generate_secret 32)
		SECONDARY_ACCESS_KEY_ID=$(generate_secret 32)
		SECONDARY_SECRET_ACCESS_KEY=$(generate_secret 32)
		;;
	*)
		echo "ERROR: Unsupported environment type: ${env_type}" >&2
		return 1
		;;
	esac

	PRIMARY_S3_ENDPOINT_URL="http://${PRIMARY_ENDPOINT_URL}"

	# Set SECONDARY S3 endpoint URL for environments that have a secondary
	if [[ -n "${SECONDARY_ENDPOINT_URL:-}" ]]; then
		SECONDARY_S3_ENDPOINT_URL="http://${SECONDARY_ENDPOINT_URL}"
	fi

	# SECONDARY only in local and production (no secondary for CI)
	if [[ "${env_type}" == "ci" ]]; then
		PRIMARY_ACCESS_KEY_ID="ci-rustfs-access-key"
		PRIMARY_SECRET_ACCESS_KEY="ci-rustfs-secret-key"
		return 0
	fi

}

function generate_secret() {
	local length="${1:-40}"
	openssl rand -base64 48 | tr -d "=+/" | cut -c1-"${length}"
}

function generate_django_secret_key() {
	# Django needs 50+ chars with special characters
	openssl rand -base64 64 | tr -d "\n"
}

function process_env_file() {
	local template="$1"
	local output="$2"
	local env_type="$3"
	local force="$4"
	local filename
	filename=$(basename "${template}")

	configure_object_store_defaults "${env_type}"

	if [[ -f "${output}" && "${force}" != "true" ]]; then
		echo "  ⏭  ${output} already exists (use --force to overwrite)"
		return 0
	fi

	echo "  ✓  Generating ${output} (from ${template})"

	local content
	content=$(cat "${template}")

	# calculate WEB_CONCURRENCY based on CPU cores: (2 x num_cores) + 1
	local num_cores
	num_cores=$(nproc 2>/dev/null || echo "2")
	local web_concurrency=$(((num_cores * 2) + 1))

	# generate secrets based on environment type
	if [[ "${env_type}" == "ci" ]]; then
		# CI: use predictable but acceptable secrets for ephemeral environments
		content="${content//:your-specific-password@/:ci-postgres-pass@}"
		content="${content//AWS_SECRET_ACCESS_KEY=<SAME AS PRIMARY>/AWS_SECRET_ACCESS_KEY=ci-rustfs-secret}"
		content="${content//CELERY_FLOWER_PASSWORD=/CELERY_FLOWER_PASSWORD=ci-flower-pass}"
		content="${content//DJANGO_ADMIN_URL=/DJANGO_ADMIN_URL=ci-admin/}"
		content="${content//DJANGO_SECRET_KEY=/DJANGO_SECRET_KEY=ci-django-secret-key-insecure-for-testing-only}"
		content="${content//OPENSEARCH_INITIAL_ADMIN_PASSWORD=/OPENSEARCH_INITIAL_ADMIN_PASSWORD=CiAdmin123!}"
		content="${content//OPENSEARCH_PASSWORD=/OPENSEARCH_PASSWORD=CiDjango123!}"
		content="${content//POSTGRES_PASSWORD=your-specific-password/POSTGRES_PASSWORD=ci-postgres-pass}"
		content="${content//SVI_SERVER_API_KEY=/SVI_SERVER_API_KEY=ci-svi-api-key-01234567890123456789abcde}" # 40 chars
	else
		# local/production: generate random secure secrets
		local django_secret_key django_admin_url flower_pass postgres_pass opensearch_admin_pass opensearch_user_pass svi_api_key
		django_secret_key=$(generate_django_secret_key)
		django_admin_url="$(generate_secret 16)/"
		flower_pass=$(generate_secret 32)
		postgres_pass=$(generate_secret 32)
		opensearch_admin_pass=$(generate_secret 32)
		opensearch_user_pass=$(generate_secret 32)
		svi_api_key=$(generate_secret 40)

		content="${content//:your-specific-password@/:${postgres_pass}@}"
		content="${content//AWS_SECRET_ACCESS_KEY=<SAME AS PRIMARY>/AWS_SECRET_ACCESS_KEY=${PRIMARY_SECRET_ACCESS_KEY}}"
		content="${content//CELERY_FLOWER_PASSWORD=/CELERY_FLOWER_PASSWORD=${flower_pass}}"
		content="${content//DJANGO_ADMIN_URL=/DJANGO_ADMIN_URL=${django_admin_url}}"
		content="${content//DJANGO_SECRET_KEY=/DJANGO_SECRET_KEY=${django_secret_key}}"
		content="${content//OPENSEARCH_INITIAL_ADMIN_PASSWORD=/OPENSEARCH_INITIAL_ADMIN_PASSWORD=${opensearch_admin_pass}}"
		content="${content//OPENSEARCH_PASSWORD=/OPENSEARCH_PASSWORD=${opensearch_user_pass}}"
		content="${content//POSTGRES_PASSWORD=your-specific-password/POSTGRES_PASSWORD=${postgres_pass}}"
		content="${content//SVI_SERVER_API_KEY=/SVI_SERVER_API_KEY=${svi_api_key}}"
	fi

	# set WEB_CONCURRENCY based on CPU cores (applies to all environments)
	content="${content//WEB_CONCURRENCY=4/WEB_CONCURRENCY=${web_concurrency}}"

	if [[ "${filename}" == "federation-shared.example.env" ]]; then
		ensure_federation_sync_drf_token "${env_type}"
		content="${content//FEDERATION_SYNC_DRF_TOKEN=/FEDERATION_SYNC_DRF_TOKEN=${FEDERATION_SYNC_DRF_TOKEN}}"
	fi

	if [[ "${filename}" == "storage.env" ]]; then
		# PRIMARY vars
		content="${content//PRIMARY_ACCESS_KEY_ID=admin/PRIMARY_ACCESS_KEY_ID=${PRIMARY_ACCESS_KEY_ID}}"
		content="${content//PRIMARY_S3_ENDPOINT_URL=http:\/\/sds-gateway-local-rustfs:9000/PRIMARY_S3_ENDPOINT_URL=${PRIMARY_S3_ENDPOINT_URL}}"
		content="${content//PRIMARY_SECRET_ACCESS_KEY=admin/PRIMARY_SECRET_ACCESS_KEY=${PRIMARY_SECRET_ACCESS_KEY}}"
		content="${content//PRIMARY_ENDPOINT_URL=sds-gateway-local-rustfs:9000/PRIMARY_ENDPOINT_URL=${PRIMARY_ENDPOINT_URL}}"

		# SECONDARY vars (local only — SeaweedFS)
		if [[ -n "${SECONDARY_ENDPOINT_URL:-}" ]]; then
			content="${content//SECONDARY_ACCESS_KEY_ID=admin/SECONDARY_ACCESS_KEY_ID=${SECONDARY_ACCESS_KEY_ID}}"
			content="${content//SECONDARY_S3_ENDPOINT_URL=http:\/\/sds-gateway-local-sfs-s3:8333/SECONDARY_S3_ENDPOINT_URL=${SECONDARY_S3_ENDPOINT_URL}}"
			content="${content//SECONDARY_SECRET_ACCESS_KEY=admin/SECONDARY_SECRET_ACCESS_KEY=${SECONDARY_SECRET_ACCESS_KEY}}"
			content="${content//SECONDARY_ENDPOINT_URL=sds-gateway-local-sfs-s3:8333/SECONDARY_ENDPOINT_URL=${SECONDARY_ENDPOINT_URL}}"
		fi

		# deprecated:
		# content="${content//AWS_ACCESS_KEY_ID=admin/AWS_ACCESS_KEY_ID=${PRIMARY_ACCESS_KEY_ID}}"
		# content="${content//AWS_SECRET_ACCESS_KEY=admin/AWS_SECRET_ACCESS_KEY=${PRIMARY_SECRET_ACCESS_KEY}}"
	fi

	if [[ "${filename}" == "storage.prod.env" ]]; then
		# PRIMARY (SeaweedFS) vars
		content="${content//PRIMARY_ACCESS_KEY_ID=admin/PRIMARY_ACCESS_KEY_ID=${PRIMARY_ACCESS_KEY_ID}}"
		content="${content//PRIMARY_S3_ENDPOINT_URL=http:\/\/sds-gateway-prod-sfs-s3:8333/PRIMARY_S3_ENDPOINT_URL=${PRIMARY_S3_ENDPOINT_URL}}"
		content="${content//PRIMARY_SECRET_ACCESS_KEY=admin/PRIMARY_SECRET_ACCESS_KEY=${PRIMARY_SECRET_ACCESS_KEY}}"
		content="${content//PRIMARY_ENDPOINT_URL=sds-gateway-prod-sfs-s3:8333/PRIMARY_ENDPOINT_URL=${PRIMARY_ENDPOINT_URL}}"
		# SECONDARY (RustFS) vars
		content="${content//SECONDARY_ACCESS_KEY_ID=minioadmin/SECONDARY_ACCESS_KEY_ID=${SECONDARY_ACCESS_KEY_ID}}"
		content="${content//SECONDARY_SECRET_ACCESS_KEY=/SECONDARY_SECRET_ACCESS_KEY=${SECONDARY_SECRET_ACCESS_KEY}}"
		if [[ -n "${SECONDARY_ROOT_PASSWORD:-}" ]]; then
			content="${content//SECONDARY_ROOT_PASSWORD=<GENERATED SECONDARY ROOT PASSWORD>/SECONDARY_ROOT_PASSWORD=${SECONDARY_ROOT_PASSWORD}}"
		fi

		# Generally, _ACCESS_KEY_ID refers to a username and _SECRET_ACCESS_KEY to a
		# secret Thus, to simplify things, we're deprecating fields with _PASSWORD
		# suffix, or prefixes MINIO_, RUSTFS_, and AWS_; keeping variable names
		# technology-agnostic

		# Table with deprecated / unused env vars safe to rename or remove in your .env
		# files:

		# PRIMARY_ROOT_PASSWORD		-> PRIMARY_SECRET_ACCESS_KEY
		# PRIMARY_ROOT_USER			-> PRIMARY_ACCESS_KEY_ID
		# SECONDARY_ROOT_PASSWORD	-> SECONDARY_SECRET_ACCESS_KEY
		# SECONDARY_ROOT_USER		-> SECONDARY_ACCESS_KEY_ID

		# AWS_ACCESS_KEY_ID 		-> PRIMARY_ACCESS_KEY_ID and SECONDARY_ACCESS_KEY_ID
		# AWS_SECRET_ACCESS_KEY 	-> PRIMARY_SECRET_ACCESS_KEY and SECONDARY_SECRET_ACCESS_KEY
		# MINIO_ROOT_PASSWORD 		-> removed: MinIO is not used anymore; otherwise should be PRIMARY/SECONDARY_SECRET_ACCESS_KEY
		# MINIO_SECRET_ACCESS_KEY 	-> removed: MinIO is not used anymore; otherwise should be PRIMARY/SECONDARY_SECRET_ACCESS_KEY
		# RUSTFS_ACCESS_KEY_ID 		-> PRIMARY/SECONDARY_ACCESS_KEY_ID depending on your setup
		# RUSTFS_ROOT_PASSWORD 		-> PRIMARY/SECONDARY_SECRET_ACCESS_KEY
		# RUSTFS_ROOT_USER 			-> PRIMARY/SECONDARY_ACCESS_ID depending on your setup
		# RUSTFS_SECRET_ACCESS_KEY 	-> PRIMARY/SECONDARY_SECRET_ACCESS_KEY depending on your setup

		# content="${content//AWS_ACCESS_KEY_ID=admin/AWS_ACCESS_KEY_ID=${PRIMARY_ACCESS_KEY_ID}}"
		# content="${content//AWS_SECRET_ACCESS_KEY=admin/AWS_SECRET_ACCESS_KEY=${PRIMARY_SECRET_ACCESS_KEY}}"
		# content="${content//MINIO_ROOT_PASSWORD=<GENERATED SECONDARY ROOT PASSWORD>/MINIO_ROOT_PASSWORD=${SECONDARY_ROOT_PASSWORD}}"
		# content="${content//MINIO_SECRET_ACCESS_KEY=<SAME AS SECONDARY_ROOT_PASSWORD>/MINIO_SECRET_ACCESS_KEY=${SECONDARY_SECRET_ACCESS_KEY}}"
		# content="${content//RUSTFS_ACCESS_KEY_ID=minioadmin/RUSTFS_ACCESS_KEY_ID=${SECONDARY_ACCESS_KEY_ID}}"
		# content="${content//RUSTFS_ROOT_PASSWORD=<GENERATED SECONDARY ROOT PASSWORD>/RUSTFS_ROOT_PASSWORD=${SECONDARY_ROOT_PASSWORD}}"
		# content="${content//RUSTFS_ROOT_USER=minioadmin/RUSTFS_ROOT_USER=${SECONDARY_ROOT_USER}}"
		# content="${content//RUSTFS_SECRET_ACCESS_KEY=<SAME AS SECONDARY_ROOT_PASSWORD>/RUSTFS_SECRET_ACCESS_KEY=${SECONDARY_SECRET_ACCESS_KEY}}"
	fi

	# write to output (never overwrite *.example.env templates)
	if [[ "${output}" == *".example.env" ]]; then
		echo "ERROR: refused to write secrets to example template: ${output}" >&2
		exit 1
	fi
	mkdir -p "$(dirname "${output}")"
	echo "${content}" >"${output}"
	chmod 600 "${output}"
}

function set_permissions() {
	declare -a env_dirs
	env_dirs=(
		"${GATEWAY_ROOT}/.envs"
		"${SFS_ROOT}/.envs"
	)
	if [[ -n "${FEDERATION_ROOT}" ]]; then
		env_dirs+=("${FEDERATION_ROOT}/.envs")
	fi
	for dir in "${env_dirs[@]}"; do
		if [ -d "${dir}" ]; then
			find "${dir}" -type f -name "*.env" -exec chmod --changes 600 {} \;
		fi
	done
	if [[ -f "${FEDERATION_SHARED_OUTPUT}" ]]; then
		chmod --changes 600 "${FEDERATION_SHARED_OUTPUT}"
	fi
}

function main() {
	local force="false"
	local env_type=""

	# parse arguments
	while [[ $# -gt 0 ]]; do
		case "$1" in
		-f | --force)
			force="true"
			shift
			;;
		-h | --help)
			usage
			;;
		local | production | ci)
			env_type="$1"
			shift
			;;
		*)
			echo "ERROR: Unknown argument: $1" >&2
			usage
			;;
		esac
	done

	if [[ -z "${env_type}" ]]; then
		echo "ERROR: Environment type required (local, production, or ci)" >&2
		usage
	fi

	echo "🔐 Generating secrets for '${env_type}' environment..."

	local target_dir_gwy="${GATEWAY_ROOT}/.envs/${env_type}"

	# process each env file from examples
	for template in "${EXAMPLE_DIR}"/*.env; do
		local filename
		filename=$(basename "${template}")

		# skip production-specific example files for non-production envs
		if [[ "${filename}" == *.prod-example.env ]]; then
			if [[ "${env_type}" == "production" ]]; then
				# use prod-example for production django.env
				if [[ "${filename}" == "django.prod-example.env" ]]; then
					process_env_file "${template}" "${target_dir_gwy}/django.env" "${env_type}" "${force}"
				fi
			fi
			continue
		fi

		# skip regular django.env for production (we use prod-example instead)
		if [[ "${env_type}" == "production" && "${filename}" == "django.env" ]]; then
			continue
		fi

		# production: use storage.prod.env as template but output as storage.env
		if [[ "${env_type}" == "production" && "${filename}" == "storage.prod.env" ]]; then
			process_env_file "${template}" "${target_dir_gwy}/storage.env" "${env_type}" "${force}"
			continue
		fi

		# skip regular storage.env for production (we use storage.prod.env instead)
		if [[ "${env_type}" == "production" && "${filename}" == "storage.env" ]]; then
			continue
		fi

		# skip storage.prod.env for local/CI
		if [[ "${env_type}" != "production" && "${filename}" == "storage.prod.env" ]]; then
			continue
		fi

		local output="${target_dir_gwy}/${filename}"
		process_env_file "${template}" "${output}" "${env_type}" "${force}"
	done

	if [[ -f "${FEDERATION_SHARED_TEMPLATE}" ]]; then
		# Read federation-shared.example.env → write repo-root federation-shared.env only
		process_env_file \
			"${FEDERATION_SHARED_TEMPLATE}" \
			"${FEDERATION_SHARED_OUTPUT}" \
			"${env_type}" \
			"${force}"
	else
		echo "  ⏭  ${FEDERATION_SHARED_TEMPLATE} not found (skipping federation-shared.env)"
	fi

	set_permissions

	echo ""
	echo "✅ Secrets generated successfully in ${target_dir_gwy}/"
	if [[ -f "${FEDERATION_SHARED_OUTPUT}" ]]; then
		echo "   Federation shared env: ${FEDERATION_SHARED_OUTPUT}"
	fi
	echo ""
	echo "Next steps:"
	if [[ "${env_type}" == "ci" ]]; then
		echo "  - Review generated secrets (safe for ephemeral CI usage)"
	else
		echo "  - Review and customize ${target_dir_gwy}/*.env as needed"
		echo "  - Set additional optional vars (AUTH0, SENTRY, etc.)"
	fi
	echo "  - Use 'just env' to check the environment setup"
	echo "  - Use 'just up' to start the stack"
}

main "$@"
