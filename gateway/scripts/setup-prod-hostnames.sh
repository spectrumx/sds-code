#!/usr/bin/env bash
# Create prod-hostnames.env on first deploy and classify the current host.
#
# Skips when the file already exists or when deploying to CI.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/common.sh"

function show_usage() {
	echo -e "Usage: ${0} [--skip]"
	echo ""
	echo "Create scripts/prod-hostnames.env on first run and optionally register"
	echo "the current hostname as a production host."
	echo ""
	echo "    --skip    Skip setup (used for CI deploys)"
	exit 0
}

function setup_prod_hostnames_interactive() {
	local example_file="${SCRIPT_DIR}/prod-hostnames.example.env"
	local target_file="${SCRIPT_DIR}/prod-hostnames.env"

	if [[ -f "${target_file}" ]]; then
		return 0
	fi

	if [[ ! -f "${example_file}" ]]; then
		log_error "Example file not found: ${example_file}"
		exit 1
	fi

	log_header "Production Hostname Setup"
	log_msg "First deploy on this machine — creating ${target_file}..."
	cp "${example_file}" "${target_file}"
	log_success "Created: ${target_file}"

	local current_hostname
	current_hostname=$(hostname)
	if [[ -z "${current_hostname}" ]]; then
		log_warning "Could not determine current hostname; leaving ${target_file} unchanged"
		return 0
	fi

	echo ""
	echo "Current hostname: ${current_hostname}"
	printf "Is this machine a production host? [y/N] "
	read -r response
	echo ""

	case "${response}" in
	y | Y | yes | Yes | YES)
		echo "${current_hostname}" >>"${target_file}"
		log_success "Registered '${current_hostname}' as a production host"
		;;
	*)
		log_msg "Treating '${current_hostname}' as a local (non-production) host"
		log_msg "To register it later: echo '${current_hostname}' >> ${target_file}"
		;;
	esac
}

function main() {
	if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
		show_usage
	fi

	if [[ "${1:-}" == "--skip" ]]; then
		return 0
	fi

	setup_prod_hostnames_interactive
}

main "$@"
