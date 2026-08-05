#!/usr/bin/env bash
# Bring up local + peer federation sync stacks for p2p testing.
# Prereq: gateway local stack can be started from ../gateway.
set -euo pipefail

FEDERATION_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_ROOT="${FEDERATION_ROOT}/../gateway"
LOCAL_COMPOSE="${FEDERATION_ROOT}/compose.local.yaml"
PEER_COMPOSE="${FEDERATION_ROOT}/compose.peer.local.yaml"
GATEWAY_COMPOSE="${GATEWAY_ROOT}/compose.local.yaml"

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"
GATEWAY_HEALTH_PATH="${GATEWAY_HEALTH_PATH:-/}"
WAIT_SECS="${WAIT_SECS:-180}"
LOCAL_SYNC_URL="${LOCAL_SYNC_URL:-http://localhost:8001/sync/health}"
PEER_SYNC_URL="${PEER_SYNC_URL:-http://localhost:8002/sync/health}"
PEER_OS_URL="${PEER_OS_URL:-http://localhost:9201/_cluster/health}"

cd "${FEDERATION_ROOT}"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '==> %s\n' "$*"; }

require_file() {
  [[ -f "$1" ]] || die "missing $1"
}

wait_http_ok() {
  local url=$1 label=$2
  local deadline=$((SECONDS + WAIT_SECS))
  info "Waiting for ${label} (${url})"
  while ((SECONDS < deadline)); do
    if curl -fsS -o /dev/null --max-time 3 "${url}"; then
      info "${label} is up"
      return 0
    fi
    sleep 2
  done
  die "${label} not healthy after ${WAIT_SECS}s: ${url}"
}

# Require /sync/health JSON status == "ok" (not merely HTTP 200/503).
wait_sync_operational() {
  local url=$1 label=$2
  local deadline=$((SECONDS + WAIT_SECS))
  info "Waiting for ${label} operational (${url})"
  while ((SECONDS < deadline)); do
    body="$(curl -fsS --max-time 3 "${url}" 2>/dev/null || true)"
    if [[ -n "${body}" ]] && printf '%s' "${body}" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'; then
      info "${label} operational"
      return 0
    fi
    sleep 2
  done
  die "${label} not operational after ${WAIT_SECS}s: ${url}"
}

restart_and_wait_sync() {
  local container=$1 url=$2 label=$3
  info "Restarting ${container} so site-hello/bootstrap see a live peer"
  docker restart "${container}" >/dev/null
  wait_sync_operational "${url}" "${label}"
}

# --- configs ---
info "Checking federation configs"
require_file "${LOCAL_COMPOSE}"
require_file "${PEER_COMPOSE}"
require_file "${FEDERATION_ROOT}/federation.toml"
require_file "${FEDERATION_ROOT}/federation.peer.toml"
require_file "${FEDERATION_ROOT}/../federation-shared.env"
require_file "${GATEWAY_ROOT}/.envs/local/opensearch.env"

# Optional sanity: peer sync URL must be Docker DNS, not localhost
if ! grep -q 'sds-federation-peer-sync' "${FEDERATION_ROOT}/federation.toml"; then
  die "federation.toml [[peers]] should use sync_service_url → sds-federation-peer-sync"
fi
if ! grep -q 'sds-federation-local-sync' "${FEDERATION_ROOT}/federation.peer.toml"; then
  die "federation.peer.toml [[peers]] should use sync_service_url → sds-federation-local-sync"
fi

# --- gateway ---
info "Ensuring gateway local stack is running"
require_file "${GATEWAY_COMPOSE}"
(
  cd "${GATEWAY_ROOT}"
  # Start if missing; no-op if already up
  COMPOSE_FILE=compose.local.yaml docker compose \
    --env-file .envs/local/opensearch.env \
    --env-file .envs/local/storage.env \
    up -d --remove-orphans
)

# External nets required by federation compose
docker network inspect sds-network-local >/dev/null 2>&1 \
  || die "network sds-network-local missing (gateway compose should create it)"
docker network inspect sds-gateway-local-opensearch-net >/dev/null 2>&1 \
  || die "network sds-gateway-local-opensearch-net missing"

wait_http_ok "${GATEWAY_URL}${GATEWAY_HEALTH_PATH}" "gateway"
docker exec sds-gateway-local-redis redis-cli ping | grep -q PONG \
  || die "gateway redis not responding"

# --- federation images + up ---
info "Building federation sync image"
docker compose -f "${LOCAL_COMPOSE}" -f "${PEER_COMPOSE}" build

info "Starting local + peer federation stacks"
docker compose -f "${LOCAL_COMPOSE}" -f "${PEER_COMPOSE}" up -d --remove-orphans

# Peer OS is slow; assert host :9201 before trusting peer sync bootstrap
wait_http_ok "${PEER_OS_URL}" "peer opensearch"
wait_sync_operational "${LOCAL_SYNC_URL}" "local sync"
wait_sync_operational "${PEER_SYNC_URL}" "peer sync"

# Local often site-hellos while peer is still starting; peer then pulls empty/missed
# lists. Restart both once peers are listening so mutual registration succeeds.
restart_and_wait_sync sds-federation-local-sync "${LOCAL_SYNC_URL}" "local sync"
restart_and_wait_sync sds-federation-peer-sync "${PEER_SYNC_URL}" "peer sync"

info "Final health"
curl -sS "${LOCAL_SYNC_URL}"
echo
curl -sS "${PEER_SYNC_URL}"
echo
info "Done. Next: just seed-peer (peer-owned docs), then docker restart sds-federation-local-sync; publish local assets for crc→peer."
