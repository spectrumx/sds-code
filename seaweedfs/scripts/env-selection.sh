#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

function is_production_host() {
    local script_dir
    script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
    local host
    host=$(hostname)
    local prod_hosts_file="${script_dir}/prod-hostnames.env"

    if [[ ! -f "${prod_hosts_file}" ]]; then
        printf '\033[33mProduction host list not found at %s: defaulting to local\033[0m\n' "${prod_hosts_file}" >&2
        printf 'Create this file to make the warning go away:\n\n\tcp %s/prod-hostnames.example.env %s\n\n' "${script_dir}" "${prod_hosts_file}" >&2
        return 1
    fi

    while read -r line; do
        line=$(echo "${line}" | xargs)
        [[ -z "${line}" || ${line:0:1} == '#' ]] && continue
        if [[ "${line}" == "${host}" ]]; then
            return 0
        fi
    done < "${prod_hosts_file}"

    return 1
}

function is_ci_env() {
    if [[ -n "${CI:-}" ]] || [[ -n "${GITHUB_ACTIONS:-}" ]] || [[ -n "${GITLAB_CI:-}" ]] || [[ -n "${BUILD_ID:-}" ]] || [[ -n "${JENKINS_URL:-}" ]]; then
        return 0
    fi
    return 1
}

function get_target_value() {
    local target="$1"
    local env_type="$2"
    local value=""

    case "${target}" in
        env)
            value="${env_type}"
            ;;
        compose_file)
            case "${env_type}" in
                production) value="compose.production.yaml" ;;
                local)      value="compose.local.yaml" ;;
                ci)         value="compose.ci.yaml" ;;
            esac
            ;;
        env_file)
            value=".env"
            ;;
        filer_container)
            case "${env_type}" in
                production) value="sds-gateway-prod-sfs-filer" ;;
                *)          value="sds-gateway-${env_type}-sfs-filer" ;;
            esac
            ;;
        master_container)
            case "${env_type}" in
                production) value="sds-gateway-prod-sfs-master" ;;
                *)          value="sds-gateway-${env_type}-sfs-master" ;;
            esac
            ;;
        s3_container)
            case "${env_type}" in
                production) value="sds-gateway-prod-sfs-s3" ;;
                *)          value="sds-gateway-${env_type}-sfs-s3" ;;
            esac
            ;;
        *)
            printf 'Unknown target: %s\n' "${target}" >&2
            exit 1
            ;;
    esac

    printf '%s' "${value}"
}

function main() {
    if [[ $# -ne 1 ]]; then
        printf 'usage: %s <env|compose_file|app_container|env_file>\n' "${0}" >&2
        exit 1
    fi

    # determine the environment type
    local target=${1:-}
    local env_type=""
    if is_production_host 2>/dev/null; then
        env_type="production"
    elif is_ci_env; then
        env_type="ci"
    else
        env_type="local"
    fi

    get_target_value "${target}" "${env_type}"

}

main "$@"
