#!/usr/bin/env bash
# Deploy SDS Gateway environment with automated setup
#
# This script automates the deployment process including secret generation,
# network creation, service startup, database migrations, and initial setup.
#
# ENVIRONMENT VARIABLES:
#   SDS_FORCE_SECRETS  - Set to 'true' to overwrite existing secrets (default: false)
#   SDS_SKIP_SECRETS   - Set to 'true' to skip secret generation (default: false)
#   SDS_SKIP_NETWORK   - Set to 'true' to skip network creation (default: false)
#   SDS_DETACH         - Set to 'true' to run in detached mode (default: true for prod)
#
# USAGE:
#   ./deploy.sh [OPTIONS] <local|production|ci>
#   SDS_SKIP_SECRETS=true ./deploy.sh local
#   SDS_FORCE_SECRETS=true SDS_DETACH=false ./deploy.sh production

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)

# shellcheck disable=SC1091
source "${SCRIPT_DIR}/common.sh"

function usage() {
    echo -e "Usage: ${0} [OPTIONS] <local|production|ci>"
    echo ""
    echo "Deploy the SDS Gateway environment following README instructions."
    echo ""
    echo -e "\e[34mThis is a high level script that automates:\e[0m"
    echo "  1. Secret generation"
    echo "  2. Docker network creation"
    echo "  3. Service deployment"
    echo "  4. Database migrations"
    echo "  5. Superuser creation (interactive)"
    echo "  6. OpenSearch index initialization"
    echo ""
    echo -e "\e[34mSteps NOT automated (require manual action):\e[0m"
    echo "  1. MinIO bucket creation"
    echo ""
    echo -e "\e[34mOPTIONS:\e[0m"
    echo "    -f, --force         Overwrite existing env files when generating secrets"
    echo "    -s, --skip-secrets  Skip secret generation (use existing secrets)"
    echo "    -n, --skip-network  Skip network creation"
    echo "    -d, --detach        Run services in detached mode (default for prod)"
    echo "    -h, --help          Show this help message"
    echo ""
    echo -e "\e[34mARGUMENTS:\e[0m"
    echo "    <local|production|ci>   Target environment to deploy"
    echo ""
    echo -e "\e[34mENVIRONMENT VARIABLES:\e[0m"
    echo "    SDS_FORCE_SECRETS   Overwrite existing secrets (true/false, default: false)"
    echo "    SDS_SKIP_SECRETS    Skip secret generation (true/false, default: false)"
    echo "    SDS_SKIP_NETWORK    Skip network creation (true/false, default: false)"
    echo "    SDS_DETACH          Run in detached mode (true/false, default: true for prod)"
    echo ""
    echo "    Note: Command-line options take precedence over environment variables."
    echo ""
    echo -e "\e[34mEXAMPLES:\e[0m"
    echo "    ${0} local                            # Quick local deploy"
    echo "    ${0} --force production               # Production deploy, regenerate secrets"
    echo "    ${0} --skip-secrets ci                # CI deploy using existing secrets"
    echo "    SDS_SKIP_SECRETS=true ${0} local      # Use env var to skip secrets"
    echo "    SDS_DETACH=false ${0} production      # Production in foreground mode"
    echo ""
    echo -e "\e[34mNOTES:\e[0m"
    echo "    - For production, ensure prod-hostnames.env is configured first"
    echo "    - Superuser creation is interactive by default"
    echo "    - MinIO bucket must be created manually via web UI (localhost:9001 or 19001)"
    echo "    - Use 'just redeploy' for quick rebuilds after initial deploy"
    exit 0
}

function create_docker_network() {
    local env_type="$1"
    local network_name="sds-network-${env_type}"

    log_header "Docker Network Setup"

    if docker network inspect "${network_name}" &>/dev/null; then
        log_msg "Network '${network_name}' already exists"
    else
        log_msg "Creating Docker network: ${network_name}"
        docker network create "${network_name}" --driver=bridge
        log_success "Network created: ${network_name}"
    fi
}

function generate_secrets() {
    local env_type="$1"
    local force="$2"

    log_header "Secret Generation"

    local force_flag=""
    if [[ "${force}" == "true" ]]; then
        force_flag="--force"
    fi

    log_msg "Generating secrets for '${env_type}' environment..."
    just generate-secrets "${env_type}" ${force_flag}
}

function build_services() {
    log_header "Building Services"
    log_msg "Pulling images and building services..."
    just build
}

function start_services_detached() {
    log_header "Starting Services"
    log_msg "Starting services in detached mode..."
    just up || true
}

function start_services_foreground() {
    log_header "Starting Services"
    log_msg "Starting services in foreground mode (Ctrl+C to stop)..."
    just up
}

function stop_services() {
    log_msg "Stopping services..."
    just down
}

function wait_for_service() {
    local container_name="$1"
    local max_attempts="${2:-30}"
    local attempt=1

    log_msg "Waiting for container '${container_name}' to be ready..."

    while [[ ${attempt} -le ${max_attempts} ]]; do
        if just dc exec "${container_name}" echo "ready" &>/dev/null; then
            log_success "Container '${container_name}' is ready"
            return 0
        fi

        if [[ $((attempt % 5)) -eq 0 ]]; then
            log_msg "Still waiting... (attempt ${attempt}/${max_attempts})"
        fi

        sleep 2
        attempt=$((attempt + 1))
    done

    log_error "Container '${container_name}' did not become ready in time"
    return 1
}

function run_migrations() {
    local container_name="$1"

    log_header "Database Migrations"

    log_msg "Running Django migrations..."
    # you probably don't need/want makemigrations at this stage; here for documentation
    # just dc exec "${container_name}" uv run manage.py makemigrations
    just dc exec "${container_name}" uv run manage.py migrate
    log_success "Migrations applied"
}

function create_superuser() {
    local container_name="$1"
    local env_type="$2"

    log_header "Superuser Creation"

    local has_superuser
    has_superuser=$(just dc exec "${container_name}" uv run manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
print('yes' if User.objects.filter(is_superuser=True).exists() else 'no')
" 2>/dev/null | tail -n1 | tr -d '[:space:]')

    if [[ "${has_superuser}" == "yes" ]]; then
        log_msg "Superuser already exists, skipping creation"
        return 0
    fi

    if [[ "${env_type}" == "ci" ]]; then
        log_msg "Creating superuser for CI environment (non-interactive)..."
        just dc exec "${container_name}" uv run manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
User.objects.create_superuser('admin', 'admin@example.com', 'ci-admin-pass')
print('Superuser created: admin / ci-admin-pass')
"
    else
        log_msg "Creating superuser (interactive)..."
        log_msg "You will be prompted for username, email, and password"
        echo ""
        just dc exec -it "${container_name}" uv run manage.py createsuperuser || {
            log_warning "Superuser creation skipped or failed"
            log_msg "You can create it later with: just dc exec -it ${container_name} uv run manage.py createsuperuser"
        }
    fi
}

function init_opensearch_indices() {
    local container_name="$1"

    log_header "OpenSearch Index Initialization"

    log_msg "Initializing OpenSearch indices..."
    just dc exec "${container_name}" uv run manage.py init_indices
    log_success "OpenSearch indices initialized"
}

function show_next_steps() {
    local env_type="$1"
    local port_prefix=""

    if [[ "${env_type}" == "production" ]]; then
        port_prefix="1"
    fi

    log_header "Deployment Complete!"

    echo ""
    echo "🎉 Gateway deployed successfully!"
    echo ""
    echo "Next steps:"
    echo ""
    echo "  1. Create MinIO bucket:"
    echo "     - Visit http://localhost:${port_prefix}9001"
    echo "     - Login with credentials from .envs/${env_type}/minio.env"
    echo "     - Create bucket named 'spectrumx'"
    echo "     - Optionally set a storage quota"
    echo ""
    echo "  2. Access the web interface:"
    echo "     - Gateway: http://localhost:${port_prefix}8000"
    echo "     - Admin panel: http://localhost:${port_prefix}8000/admin"
    echo ""
    echo "  3. Run tests to verify installation:"
    echo "     just test"
    echo ""
    echo "  4. For production API key generation:"
    echo "     - Visit http://localhost:${port_prefix}8000/users/generate-api-key"
    echo "     - Copy the key to .envs/${env_type}/django.env"
    echo ""

    if [[ "${env_type}" == "local" ]]; then
        echo "  5. Check webpack dev server:"
        echo "     http://localhost:3000/webpack-dev-server"
        echo ""
    fi

    echo "📚 For more information, see gateway/README.md"
    echo ""
}

function parse_arguments() {
    local -n args_ref=$1
    shift

    # read from environment variables first (command-line args will override)
    if [[ "${SDS_FORCE_SECRETS:-}" == "true" ]]; then
        args_ref[force_secrets]="true"
    fi
    if [[ "${SDS_SKIP_SECRETS:-}" == "true" ]]; then
        args_ref[skip_secrets]="true"
    fi
    if [[ "${SDS_SKIP_NETWORK:-}" == "true" ]]; then
        args_ref[skip_network]="true"
    fi
    if [[ "${SDS_DETACH:-}" == "true" ]]; then
        args_ref[detach]="true"
    elif [[ "${SDS_DETACH:-}" == "false" ]]; then
        args_ref[detach]="false"
    fi

    # parse command-line arguments (these override env vars)
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -f|--force)
                args_ref[force_secrets]="true"
                shift
                ;;
            -s|--skip-secrets)
                args_ref[skip_secrets]="true"
                shift
                ;;
            -n|--skip-network)
                args_ref[skip_network]="true"
                shift
                ;;
            -d|--detach)
                args_ref[detach]="true"
                shift
                ;;
            -h|--help)
                usage
                ;;
            local|production|ci)
                args_ref[env_type]="$1"
                shift
                ;;
            *)
                log_error "Unknown argument: $1"
                usage
                ;;
        esac
    done

    if [[ -z "${args_ref[env_type]}" ]]; then
        log_error "Environment type required (local, production, or ci)"
        usage
    fi

    # auto-detach for production unless explicitly overridden
    if [[ "${args_ref[env_type]}" == "production" && "${SDS_DETACH:-}" != "false" ]]; then
        args_ref[detach]="true"
    fi
}

function determine_container_name() {
    local env_type="$1"
    if [[ "${env_type}" == "production" ]]; then
        echo "sds-gateway-prod-app"
    else
        echo "sds-gateway-${env_type}-app"
    fi
}

function setup_secrets_and_network() {
    local env_type="$1"
    local skip_secrets="$2"
    local force_secrets="$3"
    local skip_network="$4"

    if [[ "${skip_secrets}" == "false" ]]; then
        generate_secrets "${env_type}" "${force_secrets}"
    else
        log_msg "Skipping secret generation (using existing secrets)"
    fi

    if [[ "${skip_network}" == "false" ]]; then
        create_docker_network "${env_type}"
    else
        log_msg "Skipping network creation"
    fi
}

function setup_database_and_services() {
    local container_name="$1"
    local env_type="$2"

    wait_for_service "${container_name}" 60 || {
        log_error "Failed to start services"
        log_msg "Check logs with: just logs"
        exit 1
    }

    run_migrations "${container_name}"
    create_superuser "${container_name}" "${env_type}"
    init_opensearch_indices "${container_name}"
}

function finalize_deployment() {
    local env_type="$1"
    local detach="$2"

    if [[ "${detach}" == "false" ]]; then
        log_header "Restarting Services in Interactive Mode"
        stop_services
        show_next_steps "${env_type}"
        start_services_foreground
    else
        show_next_steps "${env_type}"
    fi
}

function main() {
    declare -A args=(
        [force_secrets]="false"
        [skip_secrets]="false"
        [skip_network]="false"
        [detach]="false"
        [env_type]=""
    )

    parse_arguments args "$@"

    cd "${PROJECT_ROOT}"
    log_header "SDS Gateway Deployment - ${args[env_type]} environment"

    local container_name
    container_name=$(determine_container_name "${args[env_type]}")

    setup_secrets_and_network \
        "${args[env_type]}" \
        "${args[skip_secrets]}" \
        "${args[force_secrets]}" \
        "${args[skip_network]}"

    build_services
    start_services_detached

    setup_database_and_services "${container_name}" "${args[env_type]}"
    finalize_deployment "${args[env_type]}" "${args[detach]}"
}

main "$@"
