#!/usr/bin/env bash
# Deploy the SeaweedFS stack: start services, configure S3 credentials, create bucket.
#
# By default, S3 credentials are read from .envs/<env>/sfs.env.
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
#   ./deploy.sh --sfs-env /path/to/sfs.env local

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SFS_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/common.sh"

readonly DEFAULT_MAX_WAIT=60
readonly SFS_IMAGE="docker.io/chrislusf/seaweedfs:4.17_large_disk"

function show_usage() {
    echo -e "Usage: ${0} [OPTIONS] <local|production|ci>"
    echo ""
    echo "Deploy the SeaweedFS stack: start services, configure S3 credentials, create bucket."
    echo ""
    echo -e "\e[34mOPTIONS:\e[0m"
    echo "    --sfs-env <file>    Path to env file with S3 credentials"
    echo "                        (defaults to .envs/<env>/sfs.env)"
    echo "    --skip-setup        Skip credential and bucket setup"
    echo "    -h, --help          Show this help message"
    echo ""
    echo -e "\e[34mARGUMENTS:\e[0m"
    echo "    <local|production|ci>   Target environment to deploy"
    echo ""
    echo -e "\e[34mCREDENTIALS FILE FORMAT:\e[0m"
    echo "    AWS_ACCESS_KEY_ID=<key>"
    echo "    AWS_SECRET_ACCESS_KEY=<secret>"
    echo "    AWS_STORAGE_BUCKET_NAME=<bucket>"
    echo ""
    echo -e "\e[34mEXAMPLES:\e[0m"
    echo "    ${0} local"
    echo "    ${0} ci"
    echo "    ${0} --sfs-env ../gateway/.envs/production/sfs.env production"
    echo ""
    exit 0
}

function setup_data_dirs() {
    local env_type="$1"
    if [[ "${env_type}" != "local" ]]; then
        return 0
    fi

    log_header "Local Data Directory Setup"
    log_msg "Creating data directories..."
    mkdir -p "${SFS_ROOT}/data/volumes" "${SFS_ROOT}/data/filer/filerldb2"

    local uid gid
    # uid=$(id -u)
    # gid=$(id -g)
    # matches the permissions inside the container
    uid=1000
    gid=1000
    log_msg "Setting ownership to ${uid}:${gid}..."
    sudo -p "Enter password to set ownership of data directories: " \
         chown -R "${uid}:${gid}" "${SFS_ROOT}/data/volumes/" \
         &&
    sudo chown -R "${uid}:${gid}" "${SFS_ROOT}/data/"
    sudo -k
    log_success "Data directories ready"
}

function get_compose_file() {
    local env_type="$1"
    case "${env_type}" in
        production) echo "compose.production.yaml" ;;
        ci)         echo "compose.ci.yaml" ;;
        local)      echo "compose.local.yaml" ;;
    esac
}

function get_docker_compose_cmd() {
    local env_type="$1"
    local compose_file
    compose_file=$(get_compose_file "${env_type}")
    echo "COMPOSE_FILE=${compose_file} docker compose --env-file ${SFS_ROOT}/.env"
}

function start_sfs_stack() {
    local env_type="$1"
    local dc_cmd
    dc_cmd=$(get_docker_compose_cmd "${env_type}")

    log_header "Starting SeaweedFS Stack"

    log_msg "Pulling images..."
    (cd "${SFS_ROOT}" && eval "${dc_cmd} pull --ignore-buildable") || true

    log_msg "Starting services..."
    (cd "${SFS_ROOT}" && eval "${dc_cmd} up --detach --remove-orphans")
    log_success "SeaweedFS services started"
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

    printf '%s\n' "s3.configure -apply -user ${access_key} -access_key ${access_key} -secret_key ${secret_key} -actions Admin -buckets *" | \
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

    printf '%s\n' "s3.bucket.create -name ${bucket_name}" | \
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
    access_key=$(grep -E '^AWS_ACCESS_KEY_ID=' "${env_file}" | cut -d'=' -f2-)
    secret_key=$(grep -E '^AWS_SECRET_ACCESS_KEY=' "${env_file}" | cut -d'=' -f2-)
    bucket_name=$(grep -E '^AWS_STORAGE_BUCKET_NAME=' "${env_file}" | cut -d'=' -f2-)

    if [[ -z "${access_key}" || -z "${secret_key}" || -z "${bucket_name}" ]]; then
        log_error "Missing required credentials in ${env_file}"
        log_msg "Expected: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME"
        return 1
    fi

    printf '%s\n%s\n%s' "${access_key}" "${secret_key}" "${bucket_name}"
}

function parse_arguments() {
    local -n args_ref=$1
    shift

    if [[ "${SFS_SKIP_SETUP:-}" == "true" ]]; then
        args_ref[skip_setup]="true"
    fi

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --sfs-env)
                args_ref[sfs_env_file]="${2:-}"
                shift 2
                ;;
            --skip-setup)
                args_ref[skip_setup]="true"
                shift
                ;;
            -h|--help)
                show_usage
                ;;
            local|production|ci)
                args_ref[env_type]="$1"
                shift
                ;;
            *)
                log_error "Unknown argument: $1"
                show_usage
                ;;
        esac
    done

    if [[ -z "${args_ref[env_type]}" ]]; then
        log_error "Environment type required (local, production, or ci)"
        show_usage
    fi

    # default credentials file if not specified
    if [[ -z "${args_ref[sfs_env_file]}" ]]; then
        args_ref[sfs_env_file]="${SFS_ROOT}/.envs/${args_ref[env_type]}/sfs.env"
    fi
}

function main() {
    declare -A args=(
        [env_type]=""
        [sfs_env_file]=""
        [skip_setup]="false"
    )

    parse_arguments args "$@"

    cd "${SFS_ROOT}"
    log_header "SeaweedFS Deployment - ${args[env_type]} environment"

    setup_prod_hostnames "${args[env_type]}"
    setup_data_dirs "${args[env_type]}"
    start_sfs_stack "${args[env_type]}"
    wait_for_s3_health "${args[env_type]}" "${DEFAULT_MAX_WAIT}"

    if [[ "${args[skip_setup]}" == "false" ]]; then
        local creds
        creds=$(load_credentials "${args[sfs_env_file]}")
        local access_key secret_key bucket_name
        access_key=$(echo "${creds}" | sed -n '1p')
        secret_key=$(echo "${creds}" | sed -n '2p')
        bucket_name=$(echo "${creds}" | sed -n '3p')

        configure_s3_credentials "${args[env_type]}" "${access_key}" "${secret_key}"
        create_bucket "${args[env_type]}" "${bucket_name}" "${access_key}" "${secret_key}"
    else
        log_msg "Skipping credential and bucket setup (--skip-setup)"
    fi

    log_header "SeaweedFS deployment complete"
    log_msg "S3 endpoint: http://localhost:${SFS_S3_PORT:-8333}"
    log_msg "File browser: http://localhost:${SFS_FILER_PORT:-8888}"
}

main "$@"
