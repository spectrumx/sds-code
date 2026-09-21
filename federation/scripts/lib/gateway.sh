#!/usr/bin/env bash
# Gateway compose helpers. Requires FEDERATION_ROOT, GATEWAY_ROOT, SDS_ENV_TYPE from bootstrap.

GATEWAY_ENV_SELECTION="${GATEWAY_ROOT}/scripts/env-selection.sh"

gateway_compose() {
	local compose_file=$1
	shift
	local gate_env env_file
	gate_env="$("${GATEWAY_ENV_SELECTION}" env)"
	env_file="$("${GATEWAY_ENV_SELECTION}" env_file)"
	docker compose -f "${GATEWAY_ROOT}/${compose_file}" \
		--env-file "${GATEWAY_ROOT}/${env_file}" \
		--env-file "${GATEWAY_ROOT}/.envs/${gate_env}/storage.env" \
		"$@"
}

gateway_app_service() {
	case "${SDS_ENV_TYPE}" in
	production) printf '%s\n' "sds-gateway-prod-app" ;;
	*) printf '%s\n' "sds-gateway-local-app" ;;
	esac
}

gateway_compose_file() {
	case "${SDS_ENV_TYPE}" in
	production) printf '%s\n' "compose.production.yaml" ;;
	*) printf '%s\n' "compose.local.yaml" ;;
	esac
}

gateway_django_env_path() {
	printf '%s\n' "${GATEWAY_ROOT}/.envs/${SDS_ENV_TYPE}/django.env"
}

ensure_gateway_secrets() {
	local django_env
	django_env="$(gateway_django_env_path)"
	if [[ -f "${FEDERATION_ROOT}/../federation-shared.env" && -f "${django_env}" ]]; then
		return 0
	fi
	info "Generating gateway secrets (${SDS_ENV_TYPE})"
	( cd "${GATEWAY_ROOT}" && "./scripts/generate-secrets.sh" "${SDS_ENV_TYPE}" )
}

recreate_gateway_for_updated_env() {
	local compose_file app
	compose_file="$(gateway_compose_file)"
	app="$(gateway_app_service)"
	if ! docker ps --format '{{.Names}}' | grep -qx "${app}"; then
		info "Gateway app not running (skipping recreate — start gateway before onboard)"
		return 0
	fi
	info "Recreating gateway app and Celery workers (reload django.env / federation-shared.env)"
	gateway_compose "${compose_file}" up -d --force-recreate --no-deps \
		"${app}" celery-worker celery-beat
}

init_sync_token() {
	local container compose_file
	container="$(gateway_app_service)"
	compose_file="$(gateway_compose_file)"
	info "Ensuring federation sync DRF token in gateway DB"
	gateway_compose "${compose_file}" exec -T "${container}" \
		uv run manage.py init_federation_sync_token
}
