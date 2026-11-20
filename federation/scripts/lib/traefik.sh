#!/usr/bin/env bash
# Traefik conf.d route probes shared by render-site-config and federation-doctor.
set -euo pipefail

# Gateway catch-alls use Host() only; federation sync requires PathPrefix(`/sync`).
traefik_sync_route_exists_for_fqdn() {
	local fqdn=$1 conf_dir=$2
	local host_path='Host\(`'"${fqdn}"'`\)[[:space:]]*&&[[:space:]]*PathPrefix\(`/sync`\)'
	[[ -d "${conf_dir}" ]] && grep -rqE "${host_path}" "${conf_dir}" 2>/dev/null
}

traefik_wellknown_route_exists_for_fqdn() {
	local fqdn=$1 conf_dir=$2
	local host_well='Host\(`'"${fqdn}"'`\)[[:space:]]*&&[[:space:]]*.*sds-federation\.json'
	[[ -d "${conf_dir}" ]] && grep -rqE "${host_well}" "${conf_dir}" 2>/dev/null
}