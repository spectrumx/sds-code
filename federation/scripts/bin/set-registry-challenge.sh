#!/usr/bin/env bash
# Set FEDERATION_REGISTRY_CHALLENGE_TOKEN on applicant sync env and print recreate steps.
set -euo pipefail

usage() {
	cat <<'EOF'
Usage: set-registry-challenge.sh --token TOKEN (--env-file PATH | --peer | --site-env)

Writes or updates FEDERATION_REGISTRY_CHALLENGE_TOKEN=... in the target env file.
Does not recreate containers; prints the compose command to run next.

Examples:
  ./scripts/bin/set-registry-challenge.sh --token "$TOKEN" --peer
  ./scripts/bin/set-registry-challenge.sh --token "$TOKEN" --env-file .env.local
  ./scripts/bin/set-registry-challenge.sh --token "$TOKEN" --site-env

EOF
}

# shellcheck source=../lib/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/common.sh"
TOKEN=""
ENV_FILE=""

while [[ $# -gt 0 ]]; do
	case "$1" in
	--token)
		TOKEN="${2:-}"
		shift 2
		;;
	--env-file)
		ENV_FILE="${2:-}"
		shift 2
		;;
	--peer)
		ENV_FILE="${FEDERATION_ROOT}/.env.peer"
		shift
		;;
	--site-env)
		ENV_FILE="${FEDERATION_ROOT}/site.env"
		shift
		;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		echo "Unknown argument: $1" >&2
		usage
		exit 1
		;;
	esac
done

if [[ -z "${TOKEN}" ]]; then
	echo "ERROR: --token is required" >&2
	exit 1
fi

if [[ -z "${ENV_FILE}" ]]; then
	echo "ERROR: specify --env-file, --peer, or --site-env" >&2
	exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
	echo "Target file missing: ${ENV_FILE}" >&2
	echo "Hint: cp env.peer.example .env.peer or create site.env from site.example.env" >&2
	exit 1
fi

VAR_NAME="FEDERATION_REGISTRY_CHALLENGE_TOKEN"
LINE="${VAR_NAME}=${TOKEN}"

if grep -q "^${VAR_NAME}=" "${ENV_FILE}"; then
	if [[ "$(uname -s)" == "Darwin" ]]; then
		sed -i '' "s|^${VAR_NAME}=.*|${LINE}|" "${ENV_FILE}"
	else
		sed -i "s|^${VAR_NAME}=.*|${LINE}|" "${ENV_FILE}"
	fi
else
	printf '\n%s\n' "${LINE}" >>"${ENV_FILE}"
fi

echo "Updated ${ENV_FILE}"

case "${ENV_FILE}" in
*"\.env\.peer")
	echo ""
	echo "Recreate peer sync:"
	echo "  cd ${FEDERATION_ROOT}"
	echo "  docker compose -f compose.peer.remote.yaml --env-file .env.peer up -d --force-recreate"
	echo "  # local peer lab: compose.peer.local.yaml"
	;;
*"site.env")
	echo ""
	echo "Recreate production sync (example):"
	echo "  cd ${FEDERATION_ROOT} && SDS_ENV=production just up"
	;;
*)
	echo ""
	echo "Recreate local flagship/applicant sync:"
	echo "  cd ${FEDERATION_ROOT}"
	echo "  docker compose -f compose.local.yaml up -d --force-recreate sds-federation-local-sync"
	;;
esac

echo ""
echo "Preflight:"
echo '  curl -sS "https://<your-fqdn>/.well-known/sds-federation.json" | jq '"'"'{fqdn, registry_challenge}'"'"
