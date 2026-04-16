#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
GATEWAY_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
SFS_ROOT=$(cd "${GATEWAY_ROOT}/../seaweedfs" && pwd)
EXAMPLE_DIR="${GATEWAY_ROOT}/.envs/example"
MINIO_ROOT_USER="minioadmin"
MINIO_ROOT_PASSWORD=""
SFS_ACCESS_KEY_ID=""
SFS_SECRET_ACCESS_KEY=""
SFS_ENDPOINT_URL=""
SFS_S3_ENDPOINT_URL=""

function usage() {
    cat << EOF
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
    - Generated files are placed in .envs/<env>/ directory
    - Example templates are read from .envs/example/
    - Secrets are randomly generated using OpenSSL
    - CI environment uses insecure but deterministic values for ephemeral usage
EOF
    exit 0
}

function configure_object_store_defaults() {
    local env_type="$1"

    if [[ -n "${SFS_ENDPOINT_URL}" ]]; then
        return 0
    fi

    case "${env_type}" in
        local)
            SFS_ENDPOINT_URL="sds-gateway-local-sfs-s3:8333"
            ;;
        ci)
            SFS_ENDPOINT_URL="sds-gateway-ci-sfs-s3:8333"
            ;;
        production)
            SFS_ENDPOINT_URL="sds-gateway-prod-sfs-s3:8333"
            ;;
        *)
            echo "ERROR: Unsupported environment type: ${env_type}" >&2
            return 1
            ;;
    esac

    SFS_S3_ENDPOINT_URL="http://${SFS_ENDPOINT_URL}"

    if [[ "${env_type}" == "ci" ]]; then
        SFS_ACCESS_KEY_ID="ci-sfs-access-key"
        SFS_SECRET_ACCESS_KEY="ci-sfs-secret-key"
        MINIO_ROOT_PASSWORD="ci-minio-secret"
        return 0
    fi

    SFS_ACCESS_KEY_ID=$(generate_secret 20)
    SFS_SECRET_ACCESS_KEY=$(generate_secret 40)
    MINIO_ROOT_PASSWORD=$(generate_secret 40)
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

    echo "  ✓  Generating ${output}"

    local content
    content=$(cat "${template}")

    # calculate WEB_CONCURRENCY based on CPU cores: (2 x num_cores) + 1
    local num_cores
    num_cores=$(nproc 2>/dev/null || echo "2")
    local web_concurrency=$(( (num_cores * 2) + 1 ))

    # generate secrets based on environment type
    if [[ "${env_type}" == "ci" ]]; then
        # CI: use predictable but acceptable secrets for ephemeral environments
        content="${content//:your-specific-password@/:ci-postgres-pass@}"
        content="${content//AWS_SECRET_ACCESS_KEY=<SAME AS MINIO_ROOT_PASSWORD>/AWS_SECRET_ACCESS_KEY=ci-minio-secret}"
        content="${content//CELERY_FLOWER_PASSWORD=/CELERY_FLOWER_PASSWORD=ci-flower-pass}"
        content="${content//DJANGO_ADMIN_URL=/DJANGO_ADMIN_URL=ci-admin/}"
        content="${content//DJANGO_SECRET_KEY=/DJANGO_SECRET_KEY=ci-django-secret-key-insecure-for-testing-only}"
        content="${content//MINIO_ROOT_PASSWORD=<GENERATED MINIO ROOT PASSWORD>/MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}}"
        content="${content//MINIO_SECRET_ACCESS_KEY=<SAME AS MINIO_ROOT_PASSWORD>/MINIO_SECRET_ACCESS_KEY=${MINIO_ROOT_PASSWORD}}"
        content="${content//OPENSEARCH_INITIAL_ADMIN_PASSWORD=/OPENSEARCH_INITIAL_ADMIN_PASSWORD=CiAdmin123!}"
        content="${content//OPENSEARCH_PASSWORD=/OPENSEARCH_PASSWORD=CiDjango123!}"
        content="${content//POSTGRES_PASSWORD=your-specific-password/POSTGRES_PASSWORD=ci-postgres-pass}"
        content="${content//SVI_SERVER_API_KEY=/SVI_SERVER_API_KEY=ci-svi-api-key-01234567890123456789abcde}"   # 40 chars
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
        content="${content//AWS_SECRET_ACCESS_KEY=<SAME AS MINIO_ROOT_PASSWORD>/AWS_SECRET_ACCESS_KEY=${MINIO_ROOT_PASSWORD}}"
        content="${content//CELERY_FLOWER_PASSWORD=/CELERY_FLOWER_PASSWORD=${flower_pass}}"
        content="${content//DJANGO_ADMIN_URL=/DJANGO_ADMIN_URL=${django_admin_url}}"
        content="${content//DJANGO_SECRET_KEY=/DJANGO_SECRET_KEY=${django_secret_key}}"
        content="${content//MINIO_ROOT_PASSWORD=<GENERATED MINIO ROOT PASSWORD>/MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}}"
        content="${content//MINIO_SECRET_ACCESS_KEY=<SAME AS MINIO_ROOT_PASSWORD>/MINIO_SECRET_ACCESS_KEY=${MINIO_ROOT_PASSWORD}}"
        content="${content//OPENSEARCH_INITIAL_ADMIN_PASSWORD=/OPENSEARCH_INITIAL_ADMIN_PASSWORD=${opensearch_admin_pass}}"
        content="${content//OPENSEARCH_PASSWORD=/OPENSEARCH_PASSWORD=${opensearch_user_pass}}"
        content="${content//POSTGRES_PASSWORD=your-specific-password/POSTGRES_PASSWORD=${postgres_pass}}"
        content="${content//SVI_SERVER_API_KEY=/SVI_SERVER_API_KEY=${svi_api_key}}"
    fi

    # set WEB_CONCURRENCY based on CPU cores (applies to all environments)
    content="${content//WEB_CONCURRENCY=4/WEB_CONCURRENCY=${web_concurrency}}"

    if [[ "${filename}" == "sfs.env" ]]; then
        content="${content//AWS_ACCESS_KEY_ID=admin/AWS_ACCESS_KEY_ID=${SFS_ACCESS_KEY_ID}}"
        content="${content//AWS_S3_ENDPOINT_URL=http:\/\/sds-gateway-local-sfs-s3:8333/AWS_S3_ENDPOINT_URL=${SFS_S3_ENDPOINT_URL}}"
        content="${content//AWS_SECRET_ACCESS_KEY=admin/AWS_SECRET_ACCESS_KEY=${SFS_SECRET_ACCESS_KEY}}"
        content="${content//MINIO_ACCESS_KEY_ID=minioadmin/MINIO_ACCESS_KEY_ID=${MINIO_ROOT_USER}}"
        content="${content//MINIO_SECRET_ACCESS_KEY=<SAME AS MINIO_ROOT_PASSWORD>/MINIO_SECRET_ACCESS_KEY=${MINIO_ROOT_PASSWORD}}"
        content="${content//SFS_ACCESS_KEY_ID=admin/SFS_ACCESS_KEY_ID=${SFS_ACCESS_KEY_ID}}"
        content="${content//SFS_ENDPOINT_URL=sds-gateway-local-sfs-s3:8333/SFS_ENDPOINT_URL=${SFS_ENDPOINT_URL}}"
        content="${content//SFS_S3_ENDPOINT_URL=http:\/\/sds-gateway-local-sfs-s3:8333/SFS_S3_ENDPOINT_URL=${SFS_S3_ENDPOINT_URL}}"
        content="${content//SFS_SECRET_ACCESS_KEY=admin/SFS_SECRET_ACCESS_KEY=${SFS_SECRET_ACCESS_KEY}}"
    fi

    if [[ "${filename}" == "minio.env" ]]; then
        content="${content//AWS_ACCESS_KEY_ID=minioadmin/AWS_ACCESS_KEY_ID=${MINIO_ROOT_USER}}"
        content="${content//MINIO_ACCESS_KEY_ID=minioadmin/MINIO_ACCESS_KEY_ID=${MINIO_ROOT_USER}}"
        content="${content//MINIO_ROOT_USER=minioadmin/MINIO_ROOT_USER=${MINIO_ROOT_USER}}"
    fi

    # write to output
    mkdir -p "$(dirname "${output}")"
    echo "${content}" > "${output}"
    chmod 600 "${output}"
}

function generate_seaweedfs_env_file() {
    local sfs_dir="${GATEWAY_ROOT}/../seaweedfs"
    local sfs_env_example="${sfs_dir}/.envs/example/sfs.env"
    if ! [ -f "${sfs_env_example}" ]; then
        echo "ERROR: SeaweedFS env template not found at ${sfs_env_example}" >&2
        return 1
    fi
    process_env_file "${sfs_env_example}" "${1}" "${2}" "${3}"
    chmod 600 "${1}"
}

function set_permissions() {
    declare -a env_dirs
    env_dirs=(
        "${GATEWAY_ROOT}/.envs"
        "${SFS_ROOT}/.envs"
    )
    for dir in "${env_dirs[@]}"; do
        if [ -d "${dir}" ]; then
            find "${dir}" -type f -name "*.env" -exec chmod --changes 600 {} \;
        fi
    done
}

function main() {
    local force="false"
    local env_type=""

    # parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -f|--force)
                force="true"
                shift
                ;;
            -h|--help)
                usage
                ;;
            local|production|ci)
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
    local target_dir_sfs="${SFS_ROOT}/.envs/${env_type}"

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

        local output="${target_dir_gwy}/${filename}"
        process_env_file "${template}" "${output}" "${env_type}" "${force}"
    done

    generate_seaweedfs_env_file "${target_dir_sfs}/sfs.env" "${env_type}" "${force}"
    set_permissions

    echo ""
    echo "✅ Secrets generated successfully in ${target_dir_gwy}/"
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
