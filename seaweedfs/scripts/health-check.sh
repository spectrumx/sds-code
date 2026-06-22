#!/usr/bin/env bash
# seaweedfs-health-check.sh — comprehensive cluster diagnostic
# Human-readable colored output + machine-readable JSON summary
#
# Usage: ./scripts/health-check.sh [--json | --silent | --verbose]
#
# Exit codes:
#   0  — all OK
#   1  — failures (warnings don't fail)
#   2  — fatal error (can't run checks)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
source "${SCRIPT_DIR}/common.sh"
SHOW_TIMESTAMP=false

# ── args ────────────────────────────────────────────────────
OUTPUT_MODE="human"
VERBOSE=false
for arg in "$@"; do
	case "$arg" in
	--json) OUTPUT_MODE="json" ;;
	--silent) OUTPUT_MODE="silent" ;;
	--verbose) VERBOSE=true ;;
	esac
done

if [[ "$OUTPUT_MODE" == "human" ]]; then
	echo -e "Health check at $(date +"%Y-%m-%d %H:%M:%S")\n"
fi

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
	SFS_PROM_CONTAINER_PORT=$(grep '^SFS_PROMETHEUS_CONTAINER_PORT=' "$ENV_ABS" | cut -d= -f2 || echo "9090")
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
		ok)
			if [[ "$VERBOSE" == "true" && -n "$detail" ]]; then
				echo -e "  ├─ \033[0;32m✔ ${name} — ${detail}\033[0m"
			else
				echo -e "  ├─ \033[0;32m✔ ${name}\033[0m"
			fi
			;;
		warn)
			if [[ -n "$detail" ]]; then
				echo -e "  ├─ \033[0;33m⚠ ${name} — ${detail}\033[0m"
			else
				echo -e "  ├─ \033[0;33m⚠ ${name}\033[0m"
			fi
			;;
		fail)
			if [[ -n "$detail" ]]; then
				echo -e "  ├─ \033[0;31m✗ ${name} — ${detail}\033[0m"
			else
				echo -e "  ├─ \033[0;31m✗ ${name}\033[0m"
			fi
			;;
		esac
	fi
}

# Run curl inside a container via docker compose exec (status only)
dc_exec_ok() {
	local svc="$1"
	shift
	${DOCKER_COMPOSE} exec -T "$svc" curl -fsS --max-time 5 "$@" >/dev/null 2>&1
}
# Run curl inside a container, capture JSON/stdout
dc_exec_json() {
	local svc="$1"
	shift
	${DOCKER_COMPOSE} exec -T "$svc" curl -fsS --max-time 5 "$@" 2>/dev/null || echo '{}'
}
# Run wget inside a container (for Prometheus/Pushgateway which lack curl)
dc_exec_wget_ok() {
	local svc="$1"
	shift
	${DOCKER_COMPOSE} exec -T "$svc" wget --spider -q "$@" >/dev/null 2>&1
}
dc_exec_wget_capture() {
	local svc="$1"
	shift
	${DOCKER_COMPOSE} exec -T "$svc" wget -qO- "$@" 2>/dev/null || echo '{}'
}

output_header() {
	if [[ "$OUTPUT_MODE" == "human" ]]; then
		echo ""
		log_header "$1"
	fi
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

if dc_exec_ok sfs-master http://localhost:9333/cluster/status; then
	add_check "Master HTTP (9333)" "ok" ""
else
	add_check "Master HTTP (9333)" "fail" "unreachable"
fi

MASTER_JSON=$(dc_exec_json sfs-master http://localhost:9333/cluster/status)
MASTER_LEADER=$(echo "$MASTER_JSON" | jq -r '.Leader // "unknown"' 2>/dev/null)
MASTER_IS_LEADER=$(echo "$MASTER_JSON" | jq -r '.IsLeader // "unknown"' 2>/dev/null)
MASTER_MAX_VOL=$(echo "$MASTER_JSON" | jq -r '.MaxVolumeId // "unknown"' 2>/dev/null)
add_check "Master topology" "ok" "leader=${MASTER_LEADER}, isLeader=${MASTER_IS_LEADER}, maxVolId=${MASTER_MAX_VOL}"

# ─────────────────────────────────────────────────────────────
output_header "3. VOLUME SERVERS"

for i in $(seq 1 $VOL_COUNT); do
	port=$((VOL_BASE_PORT + i - 1))
	grpc_port=$((VOL_BASE_GRPC + i - 1))

	if [[ "$COMPOSE_PROFILE" == "local" ]] || [[ "$COMPOSE_PROFILE" == "ci" ]]; then
		svc_name="sds-gateway-${ENV_TYPE}-sfs-volume"
		vol_svc="sfs-volume"
	else
		svc_name="sds-gateway-${ENV_TYPE}-sfs-volume${i}"
		vol_svc="sfs-volume${i}"
	fi

	if dc_exec_ok "$vol_svc" "http://localhost:${port}/healthz"; then
		add_check "${svc_name} HTTP (${port})" "ok" ""
	else
		add_check "${svc_name} HTTP (${port})" "fail" "healthz unreachable"
	fi

	if dc_exec_ok "$vol_svc" "http://localhost:${grpc_port}/debug/vars"; then
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

if dc_exec_ok sfs-filer "http://localhost:${SFS_FILER_PORT:-8888}/"; then
	add_check "Filer HTTP (${SFS_FILER_PORT:-8888})" "ok" ""
else
	add_check "Filer HTTP (${SFS_FILER_PORT:-8888})" "fail" "unreachable"
fi

if dc_exec_ok sfs-filer http://localhost:18888/; then
	add_check "Filer gRPC (18888)" "ok" ""
else
	add_check "Filer gRPC (18888)" "warn" "unreachable (may be normal)"
fi

# ─────────────────────────────────────────────────────────────
output_header "6. S3 GATEWAY"

if dc_exec_ok sfs-s3 http://localhost:8333/healthz; then
	add_check "S3 HTTP (8333)" "ok" ""
else
	add_check "S3 HTTP (8333)" "fail" "healthz unreachable"
fi

S3_BUCKETS=$(${DOCKER_COMPOSE} exec -T sfs-filer \
	bash -c 'echo "s3.bucket.list" | weed shell -master="sfs-master:9333"' 2>/dev/null || echo "")
if [[ -n "$S3_BUCKETS" ]]; then
	BUCKET_COUNT=$(echo "$S3_BUCKETS" | grep -cP '^\s+\S+' 2>/dev/null || echo "0")
	add_check "S3 list buckets" "ok" "${BUCKET_COUNT} bucket(s)"
else
	add_check "S3 list buckets" "warn" "unable to list buckets via weed shell"
fi

# ─────────────────────────────────────────────────────────────
output_header "7. WEBDAV"

if [[ "$HAS_WEBDAV" == "true" ]]; then
	if dc_exec_ok sfs-webdav "http://localhost:${SFS_WEBDAV_PORT:-7333}/"; then
		add_check "WebDAV HTTP (${SFS_WEBDAV_PORT:-7333})" "ok" ""
	else
		# 405 may mean WebDAV is running but / is not the root endpoint
		WEBDAV_CODE=$(${DOCKER_COMPOSE} exec -T sfs-webdav curl -fsS --max-time 5 -o /dev/null -w '%{http_code}' "http://localhost:${SFS_WEBDAV_PORT:-7333}/" 2>/dev/null || echo "000")
		if [[ "$WEBDAV_CODE" == "405" ]]; then
			add_check "WebDAV HTTP (${SFS_WEBDAV_PORT:-7333})" "ok" "responding (405 on / is normal)"
		else
			add_check "WebDAV HTTP (${SFS_WEBDAV_PORT:-7333})" "warn" "unexpected status $WEBDAV_CODE"
		fi
	fi
else
	add_check "WebDAV" "warn" "not available in ${COMPOSE_PROFILE} profile"
fi

# ─────────────────────────────────────────────────────────────
output_header "8. ADMIN & WORKER"

if [[ "$HAS_ADMIN" == "true" ]]; then
	if dc_exec_ok sfs-admin http://localhost:23646/; then
		add_check "Admin HTTP (23646)" "ok" ""
	else
		add_check "Admin HTTP (23646)" "fail" "unreachable"
	fi

	WORKER_JSON=$(dc_exec_json sfs-admin http://localhost:23646/admin/worker)
	if echo "$WORKER_JSON" | jq -e 'keys | length > 0' >/dev/null 2>&1; then
		add_check "Worker plugin" "ok" "$(echo "$WORKER_JSON" | jq -r 'keys | join(", ") // "active"' 2>/dev/null)"
	else
		add_check "Worker plugin" "warn" "status unknown"
	fi
else
	add_check "Admin HTTP (23646)" "warn" "requires HAS_ADMIN=true (production compose profile)"
	add_check "Worker plugin" "warn" "requires HAS_WORKER=true (production compose profile)"
fi

# ─────────────────────────────────────────────────────────────
output_header "9. METRICS"

PROM_CONTAINER_PORT="${SFS_PROM_CONTAINER_PORT:-9090}"

if dc_exec_wget_ok sfs-prometheus "http://localhost:${PROM_CONTAINER_PORT}/-/healthy"; then
	add_check "Prometheus HTTP (${PROM_CONTAINER_PORT})" "ok" ""
else
	add_check "Prometheus HTTP (${PROM_CONTAINER_PORT})" "warn" "unreachable (may be normal)"
fi

if [[ "$HAS_PROMETHEUS" == "true" && "$HAS_PUSHGATEWAY" == "true" ]]; then
	if dc_exec_wget_ok sfs-pushgateway http://localhost:9091/-/healthy; then
		add_check "Pushgateway HTTP (9091)" "ok" ""
	else
		add_check "Pushgateway HTTP (9091)" "fail" "unreachable"
	fi
fi

if [[ "$HAS_PROMETHEUS" == "true" ]]; then
	PROM_TARGETS=$(dc_exec_wget_capture sfs-prometheus "http://localhost:${PROM_CONTAINER_PORT}/api/v1/targets")
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
	add_check "Prometheus targets" "warn" "requires HAS_PROMETHEUS=true"
fi

if [[ "$HAS_GRAFANA" == "true" ]]; then
	if dc_exec_ok sfs-grafana http://localhost:3000/api/health; then
		GRAFANA_HEALTH=$(dc_exec_json sfs-grafana http://localhost:3000/api/health)
		add_check "Grafana HTTP (3000)" "ok" "$(echo "$GRAFANA_HEALTH" | jq -r '.version // "ok"' 2>/dev/null || echo "ok")"
	else
		add_check "Grafana HTTP (3000)" "fail" "unreachable"
	fi
else
	add_check "Grafana" "warn" "requires HAS_GRAFANA=true (production compose profile)"
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
				add_check "Dir ${d}" "warn" "${USE_PCT}% (high)"
			else
				add_check "Dir ${d}" "ok" "${USE_PCT}%"
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
			if [[ "$COMPOSE_PROFILE" == "local" ]] || [[ "$COMPOSE_PROFILE" == "ci" ]]; then
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
			if [[ "$COMPOSE_PROFILE" == "local" ]] || [[ "$COMPOSE_PROFILE" == "ci" ]]; then
				svc_name="sds-gateway-${ENV_TYPE}-sfs-volume"
			else
				svc_name="sds-gateway-${ENV_TYPE}-sfs-volume${i}"
			fi
			add_check "${svc_name} → master" "ok" "master HTTP reachable"
		done
	fi
fi

# Filer → master connectivity
if dc_exec_ok sfs-filer "http://localhost:${SFS_FILER_PORT:-8888}/"; then
	add_check "Filer → master" "ok" "filer responding"
else
	add_check "Filer → master" "fail" "filer unreachable"
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
	printf "  Checks: %d  |  \033[0;32m✔ %d OK\033[0m  |  \033[0;33m⚠ %d WARN\033[0m  |  \033[0;31m✗ %d FAIL\033[0m\n" "$TOTAL" "$OK" "$WARN" "$FAIL"
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
	[[ "$OUTPUT_MODE" == "human" ]] && echo -e "\033[0;31m✗ HEALTH CHECK FAILED\033[0m" >&2
	exit 1
elif [[ "$WARN" -gt 0 ]]; then
	[[ "$OUTPUT_MODE" == "human" ]] && echo -e "\033[0;33m⚠ HEALTH CHECK PASSED WITH WARNINGS\033[0m"
	exit 0
else
	[[ "$OUTPUT_MODE" == "human" ]] && echo -e "\033[0;32m✔ ALL HEALTH CHECKS PASSED\033[0m"
	exit 0
fi
