#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

is_production_host() {
    local script_dir
    script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
    local host
    host=$(hostname)
    local prod_hosts_file="${script_dir}/prod-hostnames.env"

    if [[ ! -f "${prod_hosts_file}" ]]; then
        printf 'production host list not found at %s\n' "${prod_hosts_file}" >&2
        return 1
    fi

    while read -r line; do
        # trim leading/trailing whitespace
        line=$(echo "${line}" | xargs)
        # skip comments
        [[ -z "${line}" || ${line:0:1} == '#' ]] && continue
        # check if the line matches the current host
        if [[ "${line}" == "${host}" ]]; then
            return 0
        fi
    done < "${prod_hosts_file}"

    return 1
}

get_target_value() {
    local target=$1
    local is_prod=$2
    local local_env_file=".envs/local/opensearch.env"
    local production_env_file=".envs/production/opensearch.env"

    case "${target}" in
        env)
            if [[ "${is_prod}" == true ]]; then
                printf 'production\n'
            else
                printf 'local\n'
            fi
            ;;
        compose_file)
            if [[ "${is_prod}" == true ]]; then
                printf 'compose.production.yaml\n'
            else
                printf 'compose.local.yaml\n'
            fi
            ;;
        app_container)
            if [[ "${is_prod}" == true ]]; then
                printf 'sds-gateway-prod-app\n'
            else
                printf 'sds-gateway-local-app\n'
            fi
            ;;
        env_file)
            if [[ "${is_prod}" == true ]]; then
                printf '%s\n' "${production_env_file}"
            else
                printf '%s\n' "${local_env_file}"
            fi
            ;;
        *)
            printf 'unsupported target: %s\n' "${target}" >&2
            exit 1
            ;;
    esac
}

main() {
    if [[ $# -ne 1 ]]; then
        printf 'usage: %s <env|compose_file|app_container|env_file>\n' "${0}" >&2
        exit 1
    fi

    local target=$1
    local is_prod
    if is_production_host; then
        is_prod=true
    else
        is_prod=false
    fi

    get_target_value "${target}" "${is_prod}"
}

main "$@"
