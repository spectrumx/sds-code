#!/usr/bin/env bash

set -euo pipefail

# ==== common variables
BACKUP_NAME=$(date +%Y-%m-%d)
BACKUP_DATE=$(date +%Y-%m-%d)
ENVIRONMENT=${1:-"production"}

# ==== locations
DIR_SCRIPT="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
DIR_GATEWAY="$(dirname "${DIR_SCRIPT}")"
DIR_BACKUP="${DIR_GATEWAY}/data/backups/${BACKUP_DATE}/"
DIR_POSTGRES_BACKUP="${DIR_BACKUP}/postgres"
# DIR_OPENSEARCH_BACKUP="${DIR_BACKUP}/opensearch"

COMMON_SCRIPT="${DIR_SCRIPT}/common.sh"
COMMON_VARS="${DIR_SCRIPT}/.env.sh"

# ==== arrays and associative arrays

declare -A compose_files
compose_files=(
    ["production"]="${DIR_GATEWAY}/compose.production.yaml"
    ["local"]="${DIR_GATEWAY}/compose.local.yaml"
)

declare -A service_prefixes
service_prefixes=(
    ["production"]="sds-gateway-prod-"
    ["local"]="sds-gateway-local-"
)

if [[ ! -f "${COMMON_SCRIPT}" ]]; then
    echo "Common script not found: ${COMMON_SCRIPT}"
    exit 1
fi
# shellcheck disable=SC1090
source "${COMMON_SCRIPT}"

if [[ ! -f "${COMMON_VARS}" ]]; then
    log_error "Common variables script not found: '${COMMON_VARS}'"
    log_error "Please run e.g. 'cp ${COMMON_VARS}.example ${COMMON_VARS}' to create it, then modify its variables."
    exit 1
fi
# shellcheck disable=SC1090
source "${COMMON_VARS}"

# ==== functions

function pre_checks() {
    log_header "Running pre-checks…"
    if [[ ! -f "${compose_files[$ENVIRONMENT]}" ]]; then
        log_error "Compose file for environment '${ENVIRONMENT}' does not exist."
        exit 1
    fi
    if [[ -z "${compose_files[$ENVIRONMENT]+x}" || -z "${service_prefixes[$ENVIRONMENT]+x}" ]]; then
        log_error "Environment '${ENVIRONMENT}' is not properly configured in compose_files or service_prefixes."
        exit 1
    fi
    if [[ ! -d "${DIR_BACKUP}" ]]; then
        log_msg "Backup directory does not exist. Creating it…"
        mkdir -p "${DIR_BACKUP}"
    fi
    log_success "Pre-checks completed successfully."
}

function snapshot_postgres() {
    log_header "Snapshotting PostgreSQL…"
    TARGET_SERVICE="${service_prefixes[$ENVIRONMENT]}postgres"
    if ! docker ps --format '{{.Names}}' | grep -q "${TARGET_SERVICE}"; then
        log_error "PostgreSQL service '${TARGET_SERVICE}' is not running."
        exit 1
    fi

    mkdir -p "${DIR_POSTGRES_BACKUP}"
    dump_name="pg_dumpall.sql"
    dump_file="${DIR_POSTGRES_BACKUP}/${dump_name}"

    # get postgres environment variables from the container
    log_msg "Getting database credentials from container environment..."
    POSTGRES_USER=$(docker exec "${TARGET_SERVICE}" printenv POSTGRES_USER)

    # perform full database dump directly from the container
    log_msg "Executing full database pg_dumpall (all schemas and tables)..."

    # # https://www.postgresql.org/docs/current/app-pg-dumpall.html
    docker exec "${TARGET_SERVICE}" bash -c "pg_dumpall \
        --username ${POSTGRES_USER} \
        --file /tmp/db_dump.custom \
        --clean --if-exists \
    "

    # extract to local filesystem
    log_msg "Extracting database dump to local filesystem..."
    docker cp "${TARGET_SERVICE}:/tmp/db_dump.custom" "${dump_file}" 1>/dev/null
    docker exec "${TARGET_SERVICE}" rm "/tmp/db_dump.custom"

    # compress the dump to save space
    log_msg "Compressing database dump..."
    gzip -f "${dump_file}"
    compressed_file="${dump_file}.gz"

    # verify backup existence
    if ! [[ -f "${compressed_file}" ]]; then
        log_error "Failed to create database backup at ${compressed_file}"
        exit 1
    fi

    # verify backup size
    backup_size=$(du -h "${compressed_file}" | cut -f1)
    if [[ -z "${backup_size}" ]]; then
        log_error "Failed to determine backup size."
        exit 1
    fi

    log_success "Postgres snapshot of ${backup_size} created at '${compressed_file}'."

}

function make_read_only_when_prod() {
    if [[ "${ENVIRONMENT}" != "production" ]]; then
        log_msg "Skipping read-only permissions for non-production environment."
        return
    fi
    log_msg "Making backed files and dir read-only..."
    chmod -R a-w "${DIR_BACKUP}"
    find "${DIR_BACKUP}" -type d -exec chmod a-w {} \;
    find "${DIR_BACKUP}" -type f -exec chmod a-w {} \;
}

function snapshot_stats() {
    log_header "Snapshot statistics:"
    total_size=$(du -sh "${DIR_BACKUP}" | cut -f1)
    file_count=$(find "${DIR_BACKUP}" -type f | wc -l)

    tree "${DIR_BACKUP}"
    log_success "Snapshot ${BACKUP_NAME} created in '${DIR_BACKUP}'"
    log_success " - Number of files:    ${file_count}"
    log_success " - Storage used:       ${total_size}"
}

function transfer_to_qa_when_prod() {
    log_header "Transferring backup to QA server…"
    if [[ -z "${HOSTNAME_PROD}" || -z "${HOSTNAME_QA}" || -z "${QA_BACKUPS_PATH}" ]]; then
        log_warning "One or more required variables are not set. Skipping transfer to QA."
        return
    fi
    if [[ -z "${QA_SSH_NAME}" ]]; then
        QA_SSH_NAME="${HOSTNAME_QA}"
    fi
    hostname="$(hostname)"
    if [[ "${hostname}" != "${HOSTNAME_PROD}" ]]; then
        log_msg "Skipping transfer to QA: not running from '${HOSTNAME_PROD}'."
        return
    fi
    if [[ ! -d "${DIR_BACKUP}" ]]; then
        log_error "Backup directory does not exist: '${DIR_BACKUP}'"
        exit 1
    fi
    SOURCE_PATH="$(readlink -f "${DIR_BACKUP}/")"
    DEST_PATH="${QA_BACKUPS_PATH}/${BACKUP_NAME}" # no readlink on remote paths
    if [[ ! -d "${SOURCE_PATH}" ]]; then
        log_error "Source path does not exist: '${SOURCE_PATH}'"
        exit 1
    fi
    log_msg "Transferring backup to QA server:"
    log_msg " - Src: ${SOURCE_PATH}"
    log_msg " - Dst: ${QA_SSH_NAME}:${DEST_PATH}/"
    # shellcheck disable=SC2029
    ssh "${QA_SSH_NAME}" "mkdir -p '${DEST_PATH}'"
    rsync -avz "${SOURCE_PATH}/" "${QA_SSH_NAME}:${DEST_PATH}/"
    log_success "Backup transferred to QA successfully."
}

function main() {
    log_header "Starting $(basename "$0")…"
    log_warning "This script is under development and might not snapshot all SDS services at the moment."
    log_warning "Data of MinIO objects is not included or planned to be in this snapshot."
    pre_checks || log_fatal_and_exit "Pre-checks failed."
    snapshot_postgres || log_fatal_and_exit "Postgres snapshot failed."
    make_read_only_when_prod || log_error "Failed to set read-only permissions."
    snapshot_stats || log_error "Snapshot stats failed."
    transfer_to_qa_when_prod || log_fatal_and_exit "Transfer to QA failed."
}

main "$@"
