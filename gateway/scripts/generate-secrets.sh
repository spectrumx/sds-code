#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
EXAMPLE_DIR="${PROJECT_ROOT}/.envs/example"

usage() {
    cat << EOF
Usage: ${0} [OPTIONS] <local|production|ci>

Generate environment secrets for the gateway component.

OPTIONS:
    -f, --force         Overwrite existing env files without prompting
    -h, --help          Show this help message

ARGUMENTS:
    <local|production|ci>   Target environment to generate secrets for

EXAMPLES:
    ${0} local              # Generate local env files (skip if they exist)
    ${0} --force ci         # Generate CI env files (overwrite if exist)
    ${0} production         # Generate production env files

NOTES:
    - Generated files are placed in .envs/<env>/ directory
    - Example templates are read from .envs/example/
    - Secrets are randomly generated using OpenSSL
    - CI environment uses insecure but deterministic values for ephemeral usage
EOF
    exit 0
}

generate_secret() {
    local length="${1:-40}"
    openssl rand -base64 48 | tr -d "=+/" | cut -c1-"${length}"
}

generate_django_secret_key() {
    # Django needs 50+ chars with special characters
    openssl rand -base64 64 | tr -d "\n"
}

process_env_file() {
    local template="$1"
    local output="$2"
    local env_type="$3"
    local force="$4"

    if [[ -f "${output}" && "${force}" != "true" ]]; then
        echo "  ⏭  ${output} already exists (use --force to overwrite)"
        return 0
    fi

    echo "  ✓  Generating ${output}"

    local content
    content=$(cat "${template}")

    # calculate WEB_CONCURRENCY based on CPU cores: (2 x num_cores) + 1
    local num_cores
    num_cores=$(nproc 2>/dev/null || echo "2")
    local web_concurrency=$(( (num_cores * 2) + 1 ))

    # generate secrets based on environment type
    if [[ "${env_type}" == "ci" ]]; then
        # CI: use predictable but acceptable secrets for ephemeral environments
        content="${content//DJANGO_SECRET_KEY=/DJANGO_SECRET_KEY=ci-django-secret-key-insecure-for-testing-only}"
        content="${content//DJANGO_ADMIN_URL=/DJANGO_ADMIN_URL=ci-admin/}"
        content="${content//CELERY_FLOWER_PASSWORD=/CELERY_FLOWER_PASSWORD=ci-flower-pass}"
        content="${content//SVI_SERVER_API_KEY=/SVI_SERVER_API_KEY=ci-svi-api-key-01234567890123456789abcde}"   # 40 chars
        content="${content//MINIO_ROOT_PASSWORD=<SAME AS AWS_SECRET_ACCESS_KEY>/MINIO_ROOT_PASSWORD=ci-minio-secret}"
        content="${content//AWS_SECRET_ACCESS_KEY=<SAME AS MINIO_ROOT_PASSWORD>/AWS_SECRET_ACCESS_KEY=ci-minio-secret}"
        content="${content//POSTGRES_PASSWORD=your-specific-password/POSTGRES_PASSWORD=ci-postgres-pass}"
        content="${content//:your-specific-password@/:ci-postgres-pass@}"
        content="${content//OPENSEARCH_INITIAL_ADMIN_PASSWORD=/OPENSEARCH_INITIAL_ADMIN_PASSWORD=CiAdmin123!}"
        content="${content//OPENSEARCH_PASSWORD=/OPENSEARCH_PASSWORD=CiDjango123!}"
    else
        # local/production: generate random secure secrets
        local django_secret_key django_admin_url flower_pass minio_pass postgres_pass opensearch_admin_pass opensearch_user_pass svi_api_key
        django_secret_key=$(generate_django_secret_key)
        django_admin_url="$(generate_secret 16)/"
        flower_pass=$(generate_secret 32)
        minio_pass=$(generate_secret 40)
        postgres_pass=$(generate_secret 32)
        opensearch_admin_pass=$(generate_secret 32)
        opensearch_user_pass=$(generate_secret 32)
        svi_api_key=$(generate_secret 40)

        content="${content//DJANGO_SECRET_KEY=/DJANGO_SECRET_KEY=${django_secret_key}}"
        content="${content//DJANGO_ADMIN_URL=/DJANGO_ADMIN_URL=${django_admin_url}}"
        content="${content//CELERY_FLOWER_PASSWORD=/CELERY_FLOWER_PASSWORD=${flower_pass}}"
        content="${content//SVI_SERVER_API_KEY=/SVI_SERVER_API_KEY=${svi_api_key}}"
        content="${content//MINIO_ROOT_PASSWORD=<SAME AS AWS_SECRET_ACCESS_KEY>/MINIO_ROOT_PASSWORD=${minio_pass}}"
        content="${content//AWS_SECRET_ACCESS_KEY=<SAME AS MINIO_ROOT_PASSWORD>/AWS_SECRET_ACCESS_KEY=${minio_pass}}"
        content="${content//POSTGRES_PASSWORD=your-specific-password/POSTGRES_PASSWORD=${postgres_pass}}"
        content="${content//:your-specific-password@/:${postgres_pass}@}"
        content="${content//OPENSEARCH_INITIAL_ADMIN_PASSWORD=/OPENSEARCH_INITIAL_ADMIN_PASSWORD=${opensearch_admin_pass}}"
        content="${content//OPENSEARCH_PASSWORD=/OPENSEARCH_PASSWORD=${opensearch_user_pass}}"
    fi

    # set WEB_CONCURRENCY based on CPU cores (applies to all environments)
    content="${content//WEB_CONCURRENCY=4/WEB_CONCURRENCY=${web_concurrency}}"

    # write to output
    mkdir -p "$(dirname "${output}")"
    echo "${content}" > "${output}"
}

main() {
    local force="false"
    local env_type=""

    # parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -f|--force)
                force="true"
                shift
                ;;
            -h|--help)
                usage
                ;;
            local|production|ci)
                env_type="$1"
                shift
                ;;
            *)
                echo "ERROR: Unknown argument: $1" >&2
                usage
                ;;
        esac
    done

    if [[ -z "${env_type}" ]]; then
        echo "ERROR: Environment type required (local, production, or ci)" >&2
        usage
    fi

    echo "🔐 Generating secrets for '${env_type}' environment..."

    local target_dir="${PROJECT_ROOT}/.envs/${env_type}"

    # process each env file from examples
    for template in "${EXAMPLE_DIR}"/*.env; do
        local filename
        filename=$(basename "${template}")

        # skip production-specific example files for non-production envs
        if [[ "${filename}" == *.prod-example.env ]]; then
            if [[ "${env_type}" == "production" ]]; then
                # use prod-example for production django.env
                if [[ "${filename}" == "django.prod-example.env" ]]; then
                    process_env_file "${template}" "${target_dir}/django.env" "${env_type}" "${force}"
                fi
            fi
            continue
        fi

        # skip regular django.env for production (we use prod-example instead)
        if [[ "${env_type}" == "production" && "${filename}" == "django.env" ]]; then
            continue
        fi

        local output="${target_dir}/${filename}"
        process_env_file "${template}" "${output}" "${env_type}" "${force}"
    done

    echo ""
    echo "✅ Secrets generated successfully in ${target_dir}/"
    echo ""
    echo "Next steps:"
    if [[ "${env_type}" == "ci" ]]; then
        echo "  - Review generated secrets (safe for ephemeral CI usage)"
    else
        echo "  - Review and customize ${target_dir}/*.env as needed"
        echo "  - Set additional optional vars (AUTH0, SENTRY, etc.)"
    fi
    echo "  - Use 'just env' to check the environment setup"
    echo "  - Use 'just up' to start the stack"
}

main "$@"
