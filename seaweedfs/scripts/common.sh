#!/usr/bin/env bash

# Script with helper functions to be sourced in other scripts.

SHOW_TIMESTAMP=${SHOW_TIMESTAMP:-true}

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
	if [[ "$SHOW_TIMESTAMP" == "true" ]]; then
		echo -e "$(ts) | INFO    | ${msg}"
	else
		echo -e "${msg}"
	fi
}

function log_header() {
	local msg="$1"
	if [[ "$SHOW_TIMESTAMP" == "true" ]]; then
		echo -e "$(ts) | \033[0;34m======= ${msg}\033[0m"
	else
		echo -e "\033[0;34m${msg}\033[0m"
	fi
}

function log_success() {
	local msg="$1"
	if [[ "$SHOW_TIMESTAMP" == "true" ]]; then
		echo -e "$(ts) | \033[0;32mSUCCESS\033[0m | ${msg}"
	else
		echo -e "\033[0;32m${msg}\033[0m"
	fi
}

function log_error() {
	local msg="$1"
	if [[ "$SHOW_TIMESTAMP" == "true" ]]; then
		echo -e "$(ts) | \033[0;31mERROR   | ${msg}\033[0m" >&2
	else
		echo -e "\033[0;31m${msg}\033[0m" >&2
	fi
}

function log_warning() {
	local msg="$1"
	if [[ "$SHOW_TIMESTAMP" == "true" ]]; then
		echo -e "$(ts) | \033[0;33mWARNING | ${msg}\033[0m" >&2
	else
		echo -e "\033[0;33m${msg}\033[0m" >&2
	fi
}

function log_fatal_and_exit() {
	local msg="$1"
	log_error "${msg}"
	exit 1
}

function log_error_and_skip() {
	local msg="$1"
	log_error "${msg}"
	log_msg "Skipping this step and continuing..."
}
