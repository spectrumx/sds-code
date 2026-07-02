#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

FEDERATION_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_ENV_SCRIPT="${FEDERATION_ROOT}/../gateway/scripts/env-selection.sh"

function resolve_env_type() {
	local env_type

	if [[ -n "${SDS_ENV:-}" ]]; then
		case "${SDS_ENV}" in
		ci | local | production) env_type="${SDS_ENV}" ;;
		*)
			printf '\033[33mUnknown SDS_ENV="%s": must be ci, local, or production\033[0m\n' "${SDS_ENV}" >&2
			exit 1
			;;
		esac
	elif [[ -f "${GATEWAY_ENV_SCRIPT}" ]]; then
		env_type=$("${GATEWAY_ENV_SCRIPT}" env)
	else
		env_type='local'
	fi

	case "${env_type}" in
	ci) printf 'local\n' ;;
	*) printf '%s\n' "${env_type}" ;;
	esac
}

function get_target_value() {
	local target=$1
	local env_type=$2
	local value

	case "${target}" in
	env)
		value="${env_type}"
		;;
	compose_file)
		case "${env_type}" in
		production) value='compose.production.yaml' ;;
		local) value='compose.local.yaml' ;;
		esac
		;;
	sync_container)
		case "${env_type}" in
		production) value='sds-federation-prod-sync' ;;
		local) value='sds-federation-local-sync' ;;
		esac
		;;
	env_file)
		case "${env_type}" in
		production) value='.envs/production/sync.env' ;;
		local) value='.envs/local/sync.env' ;;
		esac
		;;
	*)
		printf 'unsupported target: %s (use env, compose_file, sync_container, or env_file)\n' "${target}" >&2
		exit 1
		;;
	esac

	if [[ "${target}" == "compose_file" && ! -f "${FEDERATION_ROOT}/${value}" ]]; then
		printf '\033[31mERROR: selected compose file "%s" does not exist\033[0m\n' "${value}" >&2
		exit 1
	fi

	printf '%s\n' "${value}"
}

function main() {
	if [[ $# -ne 1 ]]; then
		printf 'usage: %s <env|compose_file|sync_container|env_file>\n' "${0}" >&2
		exit 1
	fi

	local env_type
	env_type=$(resolve_env_type)
	get_target_value "${1}" "${env_type}"
}

main "$@"
