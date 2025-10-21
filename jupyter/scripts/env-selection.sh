#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
prod_hosts_file="${script_dir}/prod-hostnames.env"

is_production_host() {
    local host
    host=$(hostname)

    if [[ ! -f "${prod_hosts_file}" ]]; then
        return 1
    fi

    while read -r line || [[ -n "${line}" ]]; do
        line=$(echo "${line}" | xargs)
        [[ -z "${line}" || ${line:0:1} == '#' ]] && continue
        if [[ "${line}" == "${host}" ]]; then
            return 0
        fi
    done < "${prod_hosts_file}"

    return 1
}

get_target_value() {
    local target=$1
    local is_prod=$2

    local local_env_file=".envs/local/jupyterhub.env"
    local production_env_file=".envs/production/jupyterhub.env"

    local output

    case "${target}" in
        env)
            if [[ "${is_prod}" == true ]]; then
                output='production'
            else
                output='local'
            fi
            ;;
        compose_file)
            if [[ "${is_prod}" == true ]]; then
                output='compose.production.yaml'
            else
                output='compose.local.yaml'
            fi
            ;;
        env_file)
            if [[ "${is_prod}" == true ]]; then
                output="${production_env_file}"
            else
                output="${local_env_file}"
            fi
            ;;
        client_network)
            if [[ "${is_prod}" == true ]]; then
                output='sds-jupyter-prod-net-clients'
            else
                output='sds-jupyter-local-net-clients'
            fi
            ;;
        compose_project_name)
            if [[ "${is_prod}" == true ]]; then
                output='sds-jupyter-prod'
            else
                output='sds-jupyter-local'
            fi
            ;;
        *)
            printf 'unsupported target: %s\n' "${target}" >&2
            exit 1
            ;;
    esac

    if [[ "${target}" == "compose_file" && ! -f "${output}" ]]; then
        printf '\033[31mERROR: selected compose file "%s" does not exist\033[0m\n' "${output}" >&2
    fi
    if [[ "${target}" == "env_file" && ! -f "${output}" ]]; then
        printf '\033[31mERROR: selected env file "%s" does not exist\033[0m\n' "${output}" >&2
    fi

    printf '%s\n' "${output}"
}

main() {
    if [[ $# -ne 1 ]]; then
        printf 'usage: %s <env|compose_file|env_file|client_network|compose_project_name>\n' "$0" >&2
        exit 1
    fi

    local target=$1
    local is_prod=false

    if is_production_host; then
        is_prod=true
    fi

    get_target_value "${target}" "${is_prod}"
}

main "$@"
