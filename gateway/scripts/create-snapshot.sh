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
DIR_OPENSEARCH_BACKUP="${DIR_BACKUP}/opensearch"
DIR_SECRETS_BACKUP="${DIR_BACKUP}/secrets"
DIR_GIT_BACKUP="${DIR_BACKUP}/git"

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

    mkdir -p "${DIR_POSTGRES_BACKUP}" || {
        log_error "Failed to create backup directory: ${DIR_POSTGRES_BACKUP}"
        exit 1
    }
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

function snapshot_opensearch() {
    log_header "Snapshotting OpenSearch…"
    TARGET_SERVICE="${service_prefixes[$ENVIRONMENT]}opensearch"
    if ! docker ps --format '{{.Names}}' | grep -q "${TARGET_SERVICE}"; then
        log_error "OpenSearch service '${TARGET_SERVICE}' is not running."
        exit 1
    fi

    snapshot_repo="my-fs-repository"
    snapshot_name="snapshot_${BACKUP_NAME}"

    snapshot_repo_status=$(docker exec -it sds-gateway-prod-opensearch bash -c "curl -k -u "'"'"\$OPENSEARCH_ADMIN_USER:\$OPENSEARCH_INITIAL_ADMIN_PASSWORD"'"'" https://localhost:9200/_snapshot/${snapshot_repo}/" | jq .)
    if [[ "$(echo "${snapshot_repo_status}" | jq -r '._shards.successful')" != "$(echo "${snapshot_repo_status}" | jq -r '._shards.total')" ]]; then
        log_error "Snapshot repository '${snapshot_repo}' is not healthy."
        log_error "Response: ${snapshot_repo_status}"
        exit 1
    fi

    snapshot_status=$(docker exec -it sds-gateway-prod-opensearch bash -c \
        "curl -k -u "'"'"\$OPENSEARCH_ADMIN_USER:\$OPENSEARCH_INITIAL_ADMIN_PASSWORD"'"'" https://localhost:9200/_cat/snapshots/${snapshot_repo}?v&s=id" | grep "${snapshot_name}" || true)

    if [[ -z "${snapshot_status}" ]]; then
        log_msg "No existing snapshot named '${snapshot_name}' found. Proceeding to create a new snapshot."
        output_json=$(docker exec -it sds-gateway-prod-opensearch bash -c \
            "curl -k -u "'"'"\$OPENSEARCH_ADMIN_USER:\$OPENSEARCH_INITIAL_ADMIN_PASSWORD"'"'" -X PUT https://localhost:9200/_snapshot/${snapshot_repo}/${snapshot_name}?wait_for_completion=true")

        result=$(echo "${output_json}" | jq -r '.snapshot.state')

        if [[ "${result}" != "SUCCESS" ]]; then
            if echo "${output_json}" | grep -q "snapshot with the same name already exists"; then
                log_msg "Snapshot named '${snapshot_name}' already exists. Skipping recreation."
            else
                log_error "OpenSearch snapshot failed with state: ${result}"
                log_error "Response: ${output_json}"
                exit 1
            fi
        fi
    else
        log_msg "Snapshot named '${snapshot_name}' already exists. Compressing existing snapshot files."
    fi

    log_msg "Transferring snapshot files to backup directory..."

    mkdir -p "${DIR_OPENSEARCH_BACKUP}" || {
        log_error "Failed to create OpenSearch backup directory: ${DIR_OPENSEARCH_BACKUP}"
        exit 1
    }
    OPENSEARCH_SNAPSHOT_ZIP="${DIR_OPENSEARCH_BACKUP}/snapshot_${BACKUP_NAME}.zip"

    if [[ -f "${OPENSEARCH_SNAPSHOT_ZIP}" ]]; then
        log_msg "Existing snapshot zip file found at '${OPENSEARCH_SNAPSHOT_ZIP}'"
        size=$(du -h "${OPENSEARCH_SNAPSHOT_ZIP}" | cut -f1)
        log_msg "Snapshot zip size: ${size}"
        log_msg "Skipping re-creation of snapshot zip."
    else
        log_msg "No existing snapshot zip file found at '${OPENSEARCH_SNAPSHOT_ZIP}'. Proceeding to create a new one."
        mkdir -p "$(dirname "${OPENSEARCH_SNAPSHOT_ZIP}")"
        pushd "${DIR_GATEWAY}" || {
            log_error "Failed to change directory to '${DIR_GATEWAY}'"
            return 1
        }
        zip -qr "${OPENSEARCH_SNAPSHOT_ZIP}" "opensearch/data/snapshots"
        popd || true
    fi

    log_success "OpenSearch snapshot completed successfully."
}

function snapshot_secrets() {
    log_header "Snapshotting gateway secrets..."

    mkdir -p "${DIR_BACKUP}" || {
        log_error "Failed to create backup directory: ${DIR_BACKUP}"
        return 1
    }

    SECRETS_ZIP="${DIR_SECRETS_BACKUP}/secrets.zip"
    tmp_items=()

    # candidate secret locations (only include if they exist)
    candidates=(
        "${DIR_GATEWAY}/.envs"
        "${DIR_GATEWAY}/.envs/local"
        "${DIR_GATEWAY}/.envs/production"
        "${DIR_SCRIPT}/.env.sh"
        "${DIR_GATEWAY}/scripts/prod-hostnames.env"
        "${DIR_GATEWAY}/scripts/prod-hostnames.example.env"
        "${DIR_GATEWAY}/config/*.env"
    )

    for path in "${candidates[@]}"; do
        # expand globs
        for match in $(shopt -s nullglob; echo "${path}"); do
            if [[ -e "${match}" ]]; then
                tmp_items+=("${match}")
            fi
        done
    done

    if [[ ${#tmp_items[@]} -eq 0 ]]; then
        log_warning "No gateway secret files found to archive. Skipping secrets snapshot."
        return 0
    fi

    # prefer zip if available, otherwise fallback to tar.gz
    # build list of relative paths (relative to DIR_GATEWAY) so archives are portable
    rel_items=()
    for abs in "${tmp_items[@]}"; do
        # if path is under DIR_GATEWAY, make relative, otherwise copy absolute
        case "${abs}" in
            "${DIR_GATEWAY}"/*)
                rel_items+=("${abs#"${DIR_GATEWAY}"/}")
                ;;
            *)
                rel_items+=("${abs}")
                ;;
        esac
    done

    pushd "${DIR_GATEWAY}" || {
        log_error "Failed to change directory to '${DIR_GATEWAY}'"
        return 1
    }

    if command -v zip >/dev/null 2>&1; then
        log_msg "Creating secrets archive at ${SECRETS_ZIP}"
        # overwrite if exists
        if [[ -f "${SECRETS_ZIP}" ]]; then
            rm -f "${SECRETS_ZIP}"
        fi
        # zip preserves relative paths; run from DIR_GATEWAY to keep paths readable
        mkdir -p "$(dirname "${SECRETS_ZIP}")"
        zip -r "${SECRETS_ZIP}" "${rel_items[@]}"
    else
        TARBALL="${DIR_BACKUP}/secrets.tar.gz"
        log_msg "zip not available, creating tarball at '${TARBALL}'"
        # tar accepts multiple args; run from DIR_GATEWAY for relative paths
        mkdir -p "$(dirname "${TARBALL}")"
        tar -czf "${TARBALL}" "${rel_items[@]}" || {
            log_error "Failed to create tarball '${TARBALL}'"
            popd || true
            return 1
        }
        log_success "Secrets snapshot created at '${TARBALL}'"
        popd || true
        return 0
    fi

    if [[ -f "${SECRETS_ZIP}" ]]; then
        size=$(du -h "${SECRETS_ZIP}" | cut -f1)
        log_success "Secrets snapshot created at '${SECRETS_ZIP}' (${size})"
    else
        log_error "Secrets archive was not created: ${SECRETS_ZIP}"
        popd || true
        return 1
    fi

    popd || true
}

function snapshot_git() {
    log_header "Snapshotting Git repository state..."

    # determine if we're inside a git repo
    if ! command -v git >/dev/null 2>&1; then
        log_warning "git command not found; skipping git snapshot."
        return 0
    fi

    # find repository root (if any)
    pushd "${DIR_GATEWAY}" >/dev/null 2>&1 || {
        log_warning "Failed to cd to gateway dir (${DIR_GATEWAY}); skipping git snapshot."
        return 0
    }

    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        log_msg "Not a git repository: ${DIR_GATEWAY}. Skipping git snapshot."
        popd >/dev/null 2>&1 || true
        return 0
    fi

    mkdir -p "${DIR_GIT_BACKUP}" || {
        log_error "Failed to create git backup dir: ${DIR_GIT_BACKUP}"
        popd >/dev/null 2>&1 || true
        return 1
    }

    # capture branch and commit info
    branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "DETACHED")
    commit_sha=$(git rev-parse --verify HEAD 2>/dev/null || echo "none")
    git_log_file="${DIR_GIT_BACKUP}/git_info.txt"
    {
        echo "branch: ${branch}"
        echo "commit: ${commit_sha}"
        echo "date: $(date --rfc-3339=seconds)"
        echo
        git status --porcelain --branch || true
        echo
        git show --name-only --pretty=format:'%h %an %ad %s' -1 || true
    } >"${git_log_file}"

    # create an archive of the current commit (HEAD) if available
    if [[ "${commit_sha}" != "none" ]]; then
        archive_path="${DIR_GIT_BACKUP}/repo_${commit_sha}.tar.gz"
        # create archive of tracked files at HEAD
        git archive --format=tar "${commit_sha}" | gzip -c >"${archive_path}" || {
            log_warning "git archive failed; continuing without commit archive."
        }
    else
        log_msg "No HEAD commit found; skipping commit archive."
    fi

    # save uncommitted changes as a patch
    diff_file="${DIR_GIT_BACKUP}/uncommitted_changes.patch"
    git diff >"${diff_file}" || {
        log_warning "Failed to write git diff to ${diff_file}."
    }

    # also save staged but uncommitted changes (if any)
    staged_diff_file="${DIR_GIT_BACKUP}/staged_changes.patch"
    git diff --staged >"${staged_diff_file}" || true

    # record sizes
    if [[ -f "${archive_path}" ]]; then
        archive_size=$(du -h "${archive_path}" | cut -f1)
        log_success "Saved git commit archive: ${archive_path} (${archive_size})"
    fi
    if [[ -s "${diff_file}" ]]; then
        diff_size=$(du -h "${diff_file}" | cut -f1)
        log_success "Saved uncommitted changes patch: ${diff_file} (${diff_size})"
    else
        log_msg "No uncommitted changes detected."
        rm -f "${diff_file}"
    fi
    if [[ -s "${staged_diff_file}" ]]; then
        staged_size=$(du -h "${staged_diff_file}" | cut -f1)
        log_success "Saved staged changes patch: ${staged_diff_file} (${staged_size})"
    else
        rm -f "${staged_diff_file}" || true
    fi

    popd >/dev/null 2>&1 || true
}

function make_read_only_when_prod() {
    if [[ "${ENVIRONMENT}" != "production" ]]; then
        log_msg "Skipping read-only permissions for non-production environment."
        return
    fi
    log_msg "Making backed files and dir read-only..."
    chmod -R a-w "${DIR_BACKUP}/*"
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
    snapshot_opensearch || log_fatal_and_exit "OpenSearch snapshot failed."
    snapshot_secrets || log_fatal_and_exit "Secrets snapshot failed."
    snapshot_git || log_fatal_and_exit "Git snapshot failed."
    make_read_only_when_prod || log_error "Failed to set read-only permissions."
    snapshot_stats || log_error "Snapshot stats failed."
    transfer_to_qa_when_prod || log_fatal_and_exit "Transfer to QA failed."
}

main "$@"
