#!/usr/bin/env bash

# Script with helper functions to be sourced in other scripts.

# ensure the script is sourced, not executed
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "This script must be sourced. Use: source ${BASH_SOURCE[0]}" >&2
    exit 1
fi

function ts() {
    local timestamp
    timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    echo "${timestamp}"
}

function log_msg() {
    local msg="$1"
    echo -e "$(ts) | INFO    | ${msg}"
}

function log_header() {
    local msg="$1"
    echo -e "$(ts) | \033[0;34m======= ${msg}\033[0m"
}

function log_success() {
    local msg="$1"
    echo -e "$(ts) | \033[0;32mSUCCESS\033[0m | ${msg}"
}

function log_error() {
    local msg="$1"
    echo -e "$(ts) | \033[0;31mERROR   | ${msg}\033[0m" >&2
}

function log_warning() {
    local msg="$1"
    echo -e "$(ts) | \033[0;33mWARNING | ${msg}\033[0m" >&2
}

function log_fatal_and_exit() {
    local msg="$1"
    log_error "${msg}"
    exit 1
}
