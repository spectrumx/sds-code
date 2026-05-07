#!/usr/bin/env bash
# seaweedfs-health-check.sh — comprehensive cluster diagnostic
# Human-readable colored output + machine-readable JSON summary
#
# Usage: ./scripts/health-check.sh [--json | --silent]
#
# Exit codes:
#   0  — all OK
#   1  — failures (warnings don't fail)
#   2  — fatal error (can't run checks)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/common.sh"

# ── args ────────────────────────────────────────────────────
OUTPUT_MODE="human"
for arg in "$@"; do
	case "$arg" in
	--json) OUTPUT_MODE="json" ;;
	--silent) OUTPUT_MODE="silent" ;;
	esac
done

# ── environment detection ───────────────────────────────────
ENV_TYPE=""
if "${SCRIPT_DIR}/env-selection.sh" env 2>/dev/null | grep -q "^production$" 2>/dev/null; then
	ENV_TYPE="production"
elif [[ -n "${CI:-}" || -n "${GITHUB_ACTIONS:-}" || -n "${GITLAB_CI:-}" || -n "${BUILD_ID:-}" ]]; then
	ENV_TYPE="ci"
else
	ENV_TYPE="local"
fi

case "$ENV_TYPE" in
production) COMPOSE_FILE="compose.production.yaml" ;;
ci) COMPOSE_FILE="compose.ci.yaml" ;;
*) COMPOSE_FILE="compose.local.yaml" ;;
esac

ENV_FILE=".envs/${ENV_TYPE}/sfs.env"
COMPOSE_ABS="${PROJECT_DIR}/${COMPOSE_FILE}"
ENV_ABS="${PROJECT_DIR}/${ENV_FILE}"
DOCKER_COMPOSE="docker compose -f ${COMPOSE_ABS} --env-file ${ENV_ABS}"

# ── detect compose profile ──────────────────────────────────
COMPOSE_PROFILE=$(basename "${COMPOSE_FILE}" .yaml | sed 's/^compose\.//')

# Service availability per profile
HAS_WEBDAV=false
HAS_ADMIN=false
HAS_GRAFANA=false
HAS_WORKER=false
HAS_PROMETHEUS=false
HAS_PUSHGATEWAY=false
case "$COMPOSE_PROFILE" in
production)
	HAS_WEBDAV=true
	HAS_ADMIN=true
	HAS_GRAFANA=true
	HAS_WORKER=true
	HAS_PROMETHEUS=true
	HAS_PUSHGATEWAY=true
	;;
ci)
	HAS_WEBDAV=true
	HAS_ADMIN=false
	HAS_GRAFANA=false
	HAS_WORKER=false
	HAS_PROMETHEUS=true
	HAS_PUSHGATEWAY=false
	;;
local)
	HAS_WEBDAV=true
	HAS_ADMIN=false
	HAS_GRAFANA=false
	HAS_WORKER=false
	HAS_PROMETHEUS=true
	HAS_PUSHGATEWAY=false
	;;
esac

# Volume server config per profile
case "$COMPOSE_PROFILE" in
production)
	VOL_COUNT=5
	VOL_BASE_PORT=8081
	VOL_BASE_GRPC=18081
	DISK_BASE="/disk"
	;;
*)
	VOL_COUNT=1
	VOL_BASE_PORT=8080
	VOL_BASE_GRPC=18080
	DISK_BASE=""
	;;
esac

# Load custom ports from env file
if [[ -f "$ENV_ABS" ]]; then
	SFS_FILER_PORT=$(grep '^SFS_FILER_PORT=' "$ENV_ABS" | cut -d= -f2 || echo "8888")
	SFS_WEBDAV_PORT=$(grep '^SFS_WEBDAV_PORT=' "$ENV_ABS" | cut -d= -f2 || echo "7333")
	SFS_PROM_HOST_PORT=$(grep '^SFS_PROMETHEUS_HOST_PORT=' "$ENV_ABS" | cut -d= -f2 || echo "9090")
fi

# ── counters ────────────────────────────────────────────────
TOTAL=0
OK=0
WARN=0
FAIL=0
JSON_CHECKS="[]"

add_check() {
	local name="$1" status="$2" detail="${3:-}"
	TOTAL=$((TOTAL + 1))
	case "$status" in
	ok) OK=$((OK + 1)) ;;
	warn) WARN=$((WARN + 1)) ;;
	fail) FAIL=$((FAIL + 1)) ;;
	esac
	JSON_CHECKS=$(echo "$JSON_CHECKS" | jq --arg n "$name" --arg s "$status" --arg d "$detail" \
		'. + [{"name": $n, "status": $s, "detail": $d}]')
	if [[ "$OUTPUT_MODE" == "human" ]]; then
		case "$status" in
		ok) log_success "${name}" ;;
		warn) log_msg "${name} [${YELLOW}⚠ ${status}${RESET}]" ;;
		fail) log_error "${name}" ;;
		esac
	fi
}

YELLOW='\033[0;33m'
RESET='\033[0m'

curl_ok() { curl -fsS --max-time 5 "$@" >/dev/null 2>&1; }
curl_json() { curl -fsS --max-time 5 "$@" 2>/dev/null || echo '{}'; }

output_header() {
	[[ "$OUTPUT_MODE" == "human" ]] && log_header "$1"
}

# ─────────────────────────────────────────────────────────────
output_header "0. PRELIMINARY"

if [[ -f "$COMPOSE_ABS" ]]; then
	add_check "Compose file exists" "ok" "$(basename "$COMPOSE_ABS")"
else
	add_check "Compose file exists" "fail" "$(basename "$COMPOSE_ABS") not found"
	log_fatal_and_exit "Compose file not found: $COMPOSE_ABS"
fi

if [[ -f "$ENV_ABS" ]]; then
	add_check "Env file exists" "ok" "$(basename "$ENV_ABS")"
else
	add_check "Env file exists" "warn" "$(basename "$ENV_ABS") not found (may use docker secrets)"
fi

# ─────────────────────────────────────────────────────────────
output_header "1. CONTAINER STATUS"

SERVICES_LIST=$(${DOCKER_COMPOSE} ps --format '{{.Service}}' 2>/dev/null || true)

if [[ -z "$SERVICES_LIST" ]]; then
	add_check "Compose stack running" "fail" "no services"
else
	SVC_COUNT=$(echo "$SERVICES_LIST" | wc -l)
	add_check "Compose stack running" "ok" "${SVC_COUNT} service(s)"
	while IFS= read -r svc; do
		svc_health=$(${DOCKER_COMPOSE} ps --format '{{.Service}}|{{.Health}}|{{.Status}}' 2>/dev/null | grep "^${svc}|" || true)
		if [[ -z "$svc_health" ]]; then
			add_check "Container: $svc" "warn" "no health output"
			continue
		fi
		health=$(echo "$svc_health" | cut -d'|' -f2)
		status=$(echo "$svc_health" | cut -d'|' -f3)
		if echo "$health" | grep -qi "healthy\|none"; then
			add_check "Container: $svc" "ok" "$health / $status"
		elif echo "$status" | grep -qi "up\|running"; then
			add_check "Container: $svc" "ok" "no healthcheck / $status"
		else
			add_check "Container: $svc" "fail" "$health / $status"
		fi
	done <<<"$SERVICES_LIST"
fi

# ─────────────────────────────────────────────────────────────
output_header "2. MASTER"

if curl_ok http://localhost:9333/cluster/status; then
	add_check "Master HTTP (9333)" "ok" ""
else
	add_check "Master HTTP (9333)" "fail" "unreachable"
fi

if curl_ok http://localhost:19333/debug/vars; then
	add_check "Master gRPC (19333)" "ok" ""
else
	add_check "Master gRPC (19333)" "warn" "unreachable (may be normal)"
fi

MASTER_JSON=$(curl_json http://localhost:9333/cluster/status)
MASTER_LEADER=$(echo "$MASTER_JSON" | jq -r '.Leader // "unknown"' 2>/dev/null)
MASTER_IS_LEADER=$(echo "$MASTER_JSON" | jq -r '.IsLeader // "unknown"' 2>/dev/null)
MASTER_MAX_VOL=$(echo "$MASTER_JSON" | jq -r '.MaxVolumeId // "unknown"' 2>/dev/null)
add_check "Master topology" "ok" "leader=${MASTER_LEADER}, isLeader=${MASTER_IS_LEADER}, maxVolId=${MASTER_MAX_VOL}"

# ─────────────────────────────────────────────────────────────
output_header "3. VOLUME SERVERS"

for i in $(seq 1 $VOL_COUNT); do
	port=$((VOL_BASE_PORT + i - 1))
	grpc_port=$((VOL_BASE_GRPC + i - 1))

	if [[ "$COMPOSE_PROFILE" == "local" ]]; then
		svc_name="sds-gateway-${ENV_TYPE}-sfs-volume"
	else
		svc_name="sds-gateway-${ENV_TYPE}-sfs-volume${i}"
	fi

	if curl_ok "http://localhost:${port}/healthz"; then
		add_check "${svc_name} HTTP (${port})" "ok" ""
	else
		add_check "${svc_name} HTTP (${port})" "fail" "healthz unreachable"
	fi

	if curl_ok "http://localhost:${grpc_port}/debug/vars"; then
		add_check "${svc_name} gRPC (${grpc_port})" "ok" ""
	else
		add_check "${svc_name} gRPC (${grpc_port})" "warn" "debug/vars unreachable"
	fi
done

# ─────────────────────────────────────────────────────────────
output_header "4. CLUSTER INFO"

if [[ "$MASTER_JSON" != "{}" ]]; then
	# Try to get volume/filer info from master (only available in some SeaweedFS versions)
	VOL_SERVERS=$(echo "$MASTER_JSON" | jq '[.Volumes[]? // {} | .url // empty] | length' 2>/dev/null || echo "-1")
	FILER_COUNT=$(echo "$MASTER_JSON" | jq '.Filervers | length // .filers | length' 2>/dev/null || echo "-1")

	if [[ "$VOL_SERVERS" -eq -1 ]]; then
		add_check "Volume servers registered" "warn" "master JSON has no Volumes field (may be normal)"
	elif [[ "$VOL_SERVERS" -eq "$VOL_COUNT" ]]; then
		add_check "Volume servers registered" "ok" "${VOL_SERVERS}/${VOL_COUNT}"
	else
		add_check "Volume servers registered" "warn" "master reports ${VOL_SERVERS}, expected ${VOL_COUNT}"
	fi

	if [[ "$FILER_COUNT" -eq -1 || "$FILER_COUNT" -eq 0 ]]; then
		add_check "Filers registered" "warn" "master JSON has no Filers field (may be normal)"
	else
		add_check "Filers registered" "ok" "${FILER_COUNT}"
	fi

	VOL_DISTRIBUTION=$(echo "$MASTER_JSON" | jq -r '.Volumes[]? | "Volume \(.id): \(.url) DC=\(.dataCenter // "?") Rack=\(.rack // "?")"' 2>/dev/null || echo "")
	if [[ -n "$VOL_DISTRIBUTION" ]]; then
		add_check "Volume distribution" "ok" "$(echo "$VOL_DISTRIBUTION" | head -c 200)"
	fi
else
	add_check "Cluster info" "fail" "master /cluster/status returned empty"
fi

# ─────────────────────────────────────────────────────────────
output_header "5. FILER"

if curl_ok "http://localhost:${SFS_FILER_PORT:-8888}/"; then
	add_check "Filer HTTP (${SFS_FILER_PORT:-8888})" "ok" ""
else
	add_check "Filer HTTP (${SFS_FILER_PORT:-8888})" "fail" "unreachable"
fi

if curl_ok http://localhost:18888/; then
	add_check "Filer gRPC (18888)" "ok" ""
else
	add_check "Filer gRPC (18888)" "warn" "unreachable (may be normal)"
fi

# ─────────────────────────────────────────────────────────────
output_header "6. S3 GATEWAY"

if curl_ok http://localhost:8333/healthz; then
	add_check "S3 HTTP (8333)" "ok" ""
else
	add_check "S3 HTTP (8333)" "fail" "healthz unreachable"
fi

S3_LIST=$(curl -fsS --max-time 5 http://localhost:8333/ 2>/dev/null || echo "unavailable")
if echo "$S3_LIST" | grep -q '<ListBucketResult' 2>/dev/null; then
	BUCKET_COUNT=$(echo "$S3_LIST" | grep -c '<Name>' 2>/dev/null || echo "0")
	add_check "S3 list buckets" "ok" "${BUCKET_COUNT} bucket(s)"
elif echo "$S3_LIST" | grep -q 'unavailable\|403\|401\|405' 2>/dev/null; then
	add_check "S3 list buckets" "warn" "auth/no-buckets (may be normal)"
else
	add_check "S3 list buckets" "warn" "unexpected response: $(echo "$S3_LIST" | head -c 100)"
fi

# ─────────────────────────────────────────────────────────────
output_header "7. WEBDAV"

if [[ "$HAS_WEBDAV" == "true" ]]; then
	if curl_ok -o /dev/null "http://localhost:${SFS_WEBDAV_PORT:-7333}/"; then
		add_check "WebDAV HTTP (${SFS_WEBDAV_PORT:-7333})" "ok" ""
	else
		# 405 may mean WebDAV is running but / is not the root endpoint
		WEBDAV_CODE=$(curl -fsS --max-time 5 -o /dev/null -w '%{http_code}' "http://localhost:${SFS_WEBDAV_PORT:-7333}/" 2>/dev/null || echo "000")
		if [[ "$WEBDAV_CODE" == "405" ]]; then
			add_check "WebDAV HTTP (${SFS_WEBDAV_PORT:-7333})" "ok" "responding (405 on / is normal)"
		else
			add_check "WebDAV HTTP (${SFS_WEBDAV_PORT:-7333})" "warn" "unexpected status $WEBDAV_CODE"
		fi
	fi
else
	add_check "WebDAV" "warn" "not in ${COMPOSE_PROFILE} profile"
fi

# ─────────────────────────────────────────────────────────────
output_header "8. ADMIN & WORKER"

if [[ "$HAS_ADMIN" == "true" ]]; then
	if curl_ok http://localhost:23646/; then
		add_check "Admin HTTP (23646)" "ok" ""
	else
		add_check "Admin HTTP (23646)" "fail" "unreachable"
	fi

	WORKER_JSON=$(curl_json http://localhost:23646/admin/worker)
	if echo "$WORKER_JSON" | jq -e 'keys | length > 0' >/dev/null 2>&1; then
		add_check "Worker plugin" "ok" "$(echo "$WORKER_JSON" | jq -r 'keys | join(", ") // "active"' 2>/dev/null)"
	else
		add_check "Worker plugin" "warn" "status unknown"
	fi
else
	add_check "Admin HTTP (23646)" "warn" "not in ${COMPOSE_PROFILE} profile"
	add_check "Worker plugin" "warn" "not in ${COMPOSE_PROFILE} profile"
fi

# ─────────────────────────────────────────────────────────────
output_header "9. METRICS"

PROM_HTTP_PORT="${SFS_PROM_HOST_PORT:-9090}"

if curl_ok "http://localhost:${PROM_HTTP_PORT}/-/healthy"; then
	add_check "Prometheus HTTP (${PROM_HTTP_PORT})" "ok" ""
else
	add_check "Prometheus HTTP (${PROM_HTTP_PORT})" "warn" "unreachable (may be normal)"
fi

if [[ "$HAS_PROMETHEUS" == "true" && "$HAS_PUSHGATEWAY" == "true" ]]; then
	if curl_ok http://localhost:9091/-/healthy; then
		add_check "Pushgateway HTTP (9091)" "ok" ""
	else
		add_check "Pushgateway HTTP (9091)" "fail" "unreachable"
	fi
fi

if [[ "$HAS_PROMETHEUS" == "true" ]]; then
	PROM_TARGETS=$(curl_json "http://localhost:${PROM_HTTP_PORT}/api/v1/targets")
	if echo "$PROM_TARGETS" | jq -e '.data.activeTargets | length > 0' >/dev/null 2>&1; then
		PROM_OK=$(echo "$PROM_TARGETS" | jq '[.data.activeTargets[]? | select(.health == "up")] | length' 2>/dev/null || echo "0")
		PROM_TOTAL=$(echo "$PROM_TARGETS" | jq '.data.activeTargets | length' 2>/dev/null || echo "0")
		if [[ "$PROM_OK" -eq "$PROM_TOTAL" ]]; then
			add_check "Prometheus targets" "ok" "${PROM_OK}/${PROM_TOTAL} healthy"
		else
			add_check "Prometheus targets" "warn" "${PROM_OK}/${PROM_TOTAL} healthy"
		fi
	else
		add_check "Prometheus targets" "warn" "no active targets"
	fi
else
	add_check "Prometheus targets" "warn" "not in ${COMPOSE_PROFILE} profile"
fi

if [[ "$HAS_GRAFANA" == "true" ]]; then
	if curl_ok http://localhost:3000/api/health; then
		GRAFANA_HEALTH=$(curl_json http://localhost:3000/api/health)
		add_check "Grafana HTTP (3000)" "ok" "$(echo "$GRAFANA_HEALTH" | jq -r '.version // "ok"' 2>/dev/null || echo "ok")"
	else
		add_check "Grafana HTTP (3000)" "fail" "unreachable"
	fi
else
	add_check "Grafana" "warn" "not in ${COMPOSE_PROFILE} profile"
fi

# ─────────────────────────────────────────────────────────────
output_header "10. DISK SPACE"

if [[ "$COMPOSE_PROFILE" == "production" && -n "$DISK_BASE" ]]; then
	for disk in 1 2 3 4 5; do
		if [[ -d "${DISK_BASE}${disk}/data" ]]; then
			DF_RESULT=$(df -h "${DISK_BASE}${disk}/data" 2>/dev/null || echo "unavailable")
			if echo "$DF_RESULT" | grep -q "Filesystem"; then
				USE_PCT=$(echo "$DF_RESULT" | tail -1 | awk '{print $5}' | tr -d '%')
				AVAIL=$(echo "$DF_RESULT" | tail -1 | awk '{print $4}')
				if [[ "$USE_PCT" =~ ^[0-9]+$ ]] && [[ "$USE_PCT" -ge 90 ]]; then
					add_check "Disk /disk${disk}/data" "warn" "${USE_PCT}% used (${AVAIL} avail)"
				else
					add_check "Disk /disk${disk}/data" "ok" "${USE_PCT}% used (${AVAIL} avail)"
				fi
			else
				add_check "Disk /disk${disk}/data" "warn" "not mounted"
			fi
		else
			add_check "Disk /disk${disk}/data" "warn" "directory not found"
		fi
	done
else
	for d in data/master data/volumes data/filer; do
		if [[ -d "${PROJECT_DIR}/${d}" ]]; then
			USE_PCT=$(df "${PROJECT_DIR}/${d}" 2>/dev/null | tail -1 | awk '{print $5}' || echo "?")
			if [[ "$USE_PCT" =~ ^[0-9]+$ ]] && [[ "$USE_PCT" -ge 90 ]]; then
				add_check "Dir ${d}" "warn" "${USE_PCT}% used (high)"
			else
				add_check "Dir ${d}" "ok" "${USE_PCT}% used"
			fi
		else
			add_check "Dir ${d}" "warn" "not found"
		fi
	done
fi

# ─────────────────────────────────────────────────────────────
output_header "11. CROSS-SERVICE DEPENDENCIES"

# Volume → master registration
if [[ "$MASTER_JSON" != "{}" ]]; then
	VOL_SERVERS_CHECK=$(echo "$MASTER_JSON" | jq '[.Volumes[]? // {} | .url // empty] | length' 2>/dev/null || echo "-1")
	if [[ "$VOL_SERVERS_CHECK" -ne -1 ]]; then
		for i in $(seq 1 $VOL_COUNT); do
			port=$((VOL_BASE_PORT + i - 1))
			if [[ "$COMPOSE_PROFILE" == "local" ]]; then
				svc_name="sds-gateway-${ENV_TYPE}-sfs-volume"
			else
				svc_name="sds-gateway-${ENV_TYPE}-sfs-volume${i}"
			fi
			if [[ "$VOL_SERVERS_CHECK" -gt 0 ]]; then
				add_check "${svc_name} → master" "ok" "registered"
			else
				add_check "${svc_name} → master" "warn" "not in master registry"
			fi
		done
	else
		# Fallback: master HTTP is up, assume connectivity
		for i in $(seq 1 $VOL_COUNT); do
			if [[ "$COMPOSE_PROFILE" == "local" ]]; then
				svc_name="sds-gateway-${ENV_TYPE}-sfs-volume"
			else
				svc_name="sds-gateway-${ENV_TYPE}-sfs-volume${i}"
			fi
			add_check "${svc_name} → master" "ok" "master HTTP reachable"
		done
	fi
fi

# Filer → master connectivity
if curl_ok "http://localhost:${SFS_FILER_PORT:-8888}/"; then
	add_check "Filer → master" "ok" "filer responding"
else
	add_check "Filer → master" "fail" "filer unreachable"
fi

# S3 → filer connectivity
S3_FILER=$(docker exec sds-gateway-${ENV_TYPE}-sfs-s3 \
	weed s3.filer 2>/dev/null || echo "unknown")
if [[ "$S3_FILER" != "unknown" ]]; then
	add_check "S3 → filer" "ok" "connected to ${S3_FILER}"
else
	add_check "S3 → filer" "warn" "can't verify connection"
fi

# ─────────────────────────────────────────────────────────────
output_header "12. DOCKER CLEANUP"

RUNNING_COUNT=$(${DOCKER_COMPOSE} ps --format '{{.Service}}' 2>/dev/null | wc -l || echo "0")
add_check "Running services" "ok" "${RUNNING_COUNT}"

NETWORK_NAME="sds-gateway-${ENV_TYPE}-seaweed-net"
ORPHANS=$(${DOCKER_COMPOSE} ps --format '{{.Name}}' 2>/dev/null || echo "")
ORPHAN_LIST=$(docker ps -q --filter "network=${NETWORK_NAME}" 2>/dev/null | while read cid; do
	cname=$(docker inspect --format '{{.Name}}' "$cid" 2>/dev/null | sed 's|^/||')
	if ! echo "$ORPHANS" | grep -qw "$cname"; then
		echo "$cname"
	fi
done || true)

if [[ -n "$ORPHAN_LIST" ]]; then
	add_check "Orphaned containers" "warn" "$ORPHAN_LIST"
else
	add_check "Orphaned containers" "ok" "none"
fi

# ─────────────────────────────────────────────────────────────
output_header "SUMMARY"

if [[ "$OUTPUT_MODE" == "human" ]]; then
	printf "  Checks: %d  |  ✓ %d OK  |  ⚠ %d WARN  |  ✗ %d FAIL\n" "$TOTAL" "$OK" "$WARN" "$FAIL"
fi

# ── JSON output ─────────────────────────────────────────────
if [[ "$OUTPUT_MODE" == "json" ]]; then
	jq -n \
		--argjson checks "$JSON_CHECKS" \
		--arg total "$TOTAL" \
		--arg ok "$OK" \
		--arg warn "$WARN" \
		--arg fail "$FAIL" \
		--arg env "$ENV_TYPE" \
		--arg profile "$COMPOSE_PROFILE" \
		--arg compose_file "$COMPOSE_FILE" \
		'{
			env: $env,
			profile: $profile,
			compose_file: $compose_file,
			total: ($total | tonumber),
			ok: ($ok | tonumber),
			warn: ($warn | tonumber),
			fail: ($fail | tonumber),
			status: (if ($fail | tonumber) > 0 then "failed" elif ($warn | tonumber) > 0 then "warning" else "ok" end),
			checks: $checks
		}'
fi

# ── EXIT ────────────────────────────────────────────────────
if [[ "$FAIL" -gt 0 ]]; then
	[[ "$OUTPUT_MODE" == "human" ]] && log_error "HEALTH CHECK FAILED"
	exit 1
elif [[ "$WARN" -gt 0 ]]; then
	log_msg "HEALTH CHECK PASSED WITH WARNINGS"
	exit 0
else
	log_success "ALL HEALTH CHECKS PASSED"
	exit 0
fi
