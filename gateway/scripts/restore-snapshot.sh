#!/usr/bin/env bash

set -euo pipefail

# common variables
ENVIRONMENT=${1:-"production"} # QA uses the "production" env
COMMON_SCRIPT="./common.sh"
POSTGRES_DUMP_NAME="pg_dumpall.sql.gz"
DIR_SCRIPT=
DIR_SCRIPT="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
DIR_GATEWAY="$(dirname "${DIR_SCRIPT}")"
DIR_ALL_BACKUPS="${DIR_GATEWAY}/data/backups"

# source environment variables (contains HOSTNAME_QA)
# shellcheck disable=SC1091
source "${DIR_SCRIPT}/.env.sh"

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

# shellcheck disable=SC1090
source "${COMMON_SCRIPT}"

function check_environment() {
    # we must be running on the QA server
    local current_hostname
    current_hostname=$(hostname)

    if [[ "${current_hostname}" != "${HOSTNAME_QA}" ]]; then
        log_error "This script can only be run on the QA server (${HOSTNAME_QA})."
        log_error "Current hostname is: ${current_hostname}"
        exit 1
    fi

    log_msg "Running on QA server. Proceeding with restoration..."
}

function get_latest_backup() {
    if [[ ! -d "${DIR_ALL_BACKUPS}" ]]; then
        log_error "Backup directory does not exist: ${DIR_ALL_BACKUPS}"
        exit 1
    fi

    # find newest directory in the form "${DIR_ALL_BACKUPS}/YYYY-MM-DD/"
    local latest_backup_dir
    latest_backup_dir=$(find "${DIR_ALL_BACKUPS}" -mindepth 1 -maxdepth 1 -type d | /usr/bin/grep -E '.*/[0-9]{4}-[0-9]{2}-[0-9]{2}$' | sort -r | head -n 1)

    if [[ -z "${latest_backup_dir}" ]]; then
        log_error "No backup directories found in '${DIR_ALL_BACKUPS}'"
        ls -alh "${DIR_ALL_BACKUPS}" || true
        exit 1
    fi
    if [[ ! -d "${latest_backup_dir}" ]]; then
        log_error "Latest backup directory is not a directory: '${latest_backup_dir}'"
        ls -alh "$(dirname "${latest_backup_dir}")" || true
        exit 1
    fi

    echo "${latest_backup_dir}"
}

function ask_confirmation_or_exit() {
    local backup_file=$1
    local backup_date
    backup_date=$(basename "${backup_file}" | sed 's/\.sql\.gz$//')

    log_warning "WARNING: This will REPLACE the current database with backup from: ${backup_date}"
    log_error "DO NOT RUN IN PRODUCTION | This machine is: '$(hostname)'"
    log_warning "All current data will be lost!"

    read -rp "Are you sure you want to continue? (y/N): " confirmation

    if [[ "${confirmation}" != "y" ]]; then
        log_msg "Restoration canceled by user."
        exit 0
    fi

    log_msg "Confirmation received. Proceeding with restoration..."
}

function restore_postgres() {
    local backup_file=$1
    local TARGET_SERVICE="${service_prefixes[${ENVIRONMENT}]}postgres"
    declare -a services_using_db
    services_using_db=(
        "${service_prefixes[${ENVIRONMENT}]}app"
    )

    # check if postgres service is running
    if ! docker ps --format '{{.Names}}' | grep -q "${TARGET_SERVICE}"; then
        log_error "PostgreSQL service '${TARGET_SERVICE}' is not running."
        exit 1
    fi

    # get postgres environment variables from the container
    log_msg "Getting database credentials from container environment..."
    POSTGRES_USER=$(docker exec "${TARGET_SERVICE}" printenv POSTGRES_USER)

    # unzip the backup file to a temporary location
    local temp_file="/tmp/db_restore.sql"
    log_msg "Uncompressing backup file..."
    gunzip -c "${backup_file}" >"${temp_file}"

    # copy the backup into the container
    log_msg "Copying backup file to container..."
    docker cp "${temp_file}" "${TARGET_SERVICE}:/tmp/db_restore.sql"

    # stop all services that use the database
    log_msg "Stopping dependent services..."
    for service in "${services_using_db[@]}"; do
        if docker ps --format '{{.Names}}' | grep -q "${service}"; then
            log_msg "\tStopping service: ${service}"
            docker compose -f "${compose_files[${ENVIRONMENT}]}" stop "${service}" --timeout 20
        else
            log_msg "\tService '${service}' is already stopped."
        fi
    done

    log_msg "Terminating existing database connections..."
    docker exec "${TARGET_SERVICE}" bash -c "psql -U ${POSTGRES_USER} -c 'SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IS NOT NULL AND pid <> pg_backend_pid();'"

    log_msg "Restoring database from backup..."
    docker exec "${TARGET_SERVICE}" bash -c "psql -U ${POSTGRES_USER} -f /tmp/db_restore.sql postgres"

    # clean up
    log_msg "Cleaning up temporary files..."
    rm -f "${temp_file}"
    docker exec "${TARGET_SERVICE}" bash -c "rm -f /tmp/db_restore.sql"

    # restart dependent services
    log_msg "Restarting dependent services..."
    for service in "${services_using_db[@]}"; do
        if ! docker ps --format '{{.Names}}' | grep -q "${service}"; then
            log_msg "\tStarting service: ${service}"
            docker compose -f "${compose_files[${ENVIRONMENT}]}" up -d "${service}"
        else
            log_msg "\tService '${service}' is already running."
        fi
    done

    log_success "Database restoration completed successfully!"
}

function main() {
    echo "Starting $(basename "$0")..."
    check_environment

    local latest_backup
    latest_backup=$(get_latest_backup)

    log_msg "Found latest backup: ${latest_backup}"
    ask_confirmation_or_exit "${latest_backup}"
    restore_postgres "${latest_backup}/postgres/${POSTGRES_DUMP_NAME}"
}

main "$@"
