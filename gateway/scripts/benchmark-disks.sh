#!/usr/bin/env bash

set -euo pipefail
IFS=$'\n\t'

# Benchmarking script based on MinIO's hardware checklist:
# https://min.io/docs/minio/container/operations/checklists/hardware.html#minio-hardware-checklist

# configure these
LOG_DIR="${LOG_DIR:-./logs}"
DISK_BASE="${DISK_BASE:-/disk}"
DISK_COUNT="${DISK_COUNT:-8}"

function _log_ts() {
    # use ANSI escape code \033[0;32m for green, \033[0m to reset; only timestamp is colored
    echo -e "\033[0;32m$(date '+%Y-%m-%d %H:%M:%S %z')\033[0m | $1"
}

function log() {
    _log_ts "$1" | tee -a "${LOG_DIR}/benchmark-disks.log"
}

function bench_writes() {
    for i in $(seq 1 "${DISK_COUNT}"); do
        disk_path="${DISK_BASE}${i}/testfile"
        log "Starting write benchmark on ${disk_path} (${i} / ${DISK_COUNT})"
        sudo dd \
            if=/dev/zero \
            of="${disk_path}" \
            bs=128k count=20000 \
            oflag=direct conv=fdatasync |&
            tee "${LOG_DIR}/dd-write-drive${i}.txt"
        log "Completed write benchmark on ${disk_path}"
    done
    log "All write benchmarks completed"
}

function bench_reads() {
    for i in $(seq 1 "${DISK_COUNT}"); do
        disk_path="${DISK_BASE}${i}/testfile"
        log "Starting read benchmark on ${disk_path} (${i} / ${DISK_COUNT})"
        sudo dd \
            if="${disk_path}" \
            of=/dev/null \
            bs=128k \
            iflag=direct |&
            tee "${LOG_DIR}/dd-read-drive${i}.txt"
        log "Completed read benchmark on ${disk_path}"
    done
    log "All read benchmarks completed"
}

function cleanup() {
    log "Cleaning up test files"
    for i in $(seq 1 "${DISK_COUNT}"); do
        disk_path="${DISK_BASE}${i}/testfile"
        if [[ -f "${disk_path}" ]]; then
            sudo rm -vf "${disk_path}"
        else
            log "No test file found at: ${disk_path}"
        fi
    done
    log "Cleanup completed"
}

function main() {
    mkdir -p "${LOG_DIR}" || {
        echo -e "\033[0;31mFailed to create log directory: ${LOG_DIR}\033[0m"
        exit 1
    }
    # bench_writes
    # bench_reads
    cleanup
    if command -v tree &>/dev/null; then
        tree "${LOG_DIR}/"
    else
        ls -alh "${LOG_DIR}/"
    fi
}

main
