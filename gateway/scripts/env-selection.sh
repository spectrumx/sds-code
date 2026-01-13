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
        printf '\033[33mProduction host list not found at %s: defaulting to local\033[0m\n' "${prod_hosts_file}" >&2
        printf 'Create this file to make the warning go away:\n\n\tcp %s/prod-hostnames.example.env %s\n\n' "${script_dir}" "${prod_hosts_file}" >&2
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

is_ci_env() {
    if [[ -n "${CI:-}" ]] || [[ -n "${GITHUB_ACTIONS:-}" ]] || [[ -n "${GITLAB_CI:-}" ]] || [[ -n "${BUILD_ID:-}" ]] || [[ -n "${JENKINS_URL:-}" ]]; then
        return 0
    fi
    return 1
}

get_target_value() {
    local target=$1
    local env_type=$2
    local local_env_file=".envs/local/opensearch.env"
    local production_env_file=".envs/production/opensearch.env"
    local ci_env_file=".envs/ci/opensearch.env"
    local value

    case "${target}" in
        env)
            value="${env_type}"
            ;;
        compose_file)
            case "${env_type}" in
                production)
                    value='compose.production.yaml'
                    ;;
                local)
                    value='compose.local.yaml'
                    ;;
                ci)
                    value='compose.ci.yaml'
                    ;;
            esac
            ;;
        app_container)
            case "${env_type}" in
                ci)
                    value='sds-gateway-ci-app'
                    ;;
                local)
                    value='sds-gateway-local-app'
                    ;;
                production)
                    value='sds-gateway-prod-app'
                    ;;
                *)
                    printf 'unsupported environment type: %s\n' "${env_type}" >&2
                    exit 1
                    ;;
            esac
            ;;
        env_file)
            case "${env_type}" in
                ci)
                    value="${ci_env_file}"
                    ;;
                local)
                    value="${local_env_file}"
                    ;;
                production)
                    value="${production_env_file}"
                    ;;
                *)
                    printf 'unsupported environment type: %s\n' "${env_type}" >&2
                    exit 1
                    ;;
            esac
            ;;
        *)
            printf 'unsupported target: %s\n' "${target}" >&2
            exit 1
            ;;
    esac

    if [[ "${target}" == "compose_file" && ! -f "${value}" ]]; then
        printf '\033[31mERROR: selected compose file "%s" does not exist\033[0m\n' "${value}" >&2
    fi
    if [[ "${target}" == "env_file" && ! -f "${value}" ]]; then
        printf '\033[31mERROR: selected env file "%s" does not exist\033[0m\n' "${value}" >&2
    fi

    printf '%s\n' "${value}"
}

main() {
    if [[ $# -ne 1 ]]; then
        printf 'usage: %s <env|compose_file|app_container|env_file>\n' "${0}" >&2
        exit 1
    fi

    local target=$1
    local env_type
    if is_ci_env; then
        env_type='ci'
    elif is_production_host; then
        env_type='production'
    else
        env_type='local'
    fi

    get_target_value "${target}" "${env_type}"
}

main "$@"
