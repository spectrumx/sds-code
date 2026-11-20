#!/usr/bin/env bash
# Registry join helper: set verification challenge, then preflight before mothership apply/verify.
set -euo pipefail

usage() {
	cat <<'EOF'
Usage:
  federation-join-registry.sh --token TOKEN (--env-file PATH | --peer | --site-env)
  federation-join-registry.sh --preflight (--env-file PATH | --peer | --site-env)

Step 1 — paste token from the mothership application page, recreate sync when prompted.
Step 2 — after sync is recreated, run with --preflight (runs federation-doctor preflight_apply).

Examples:
  ./scripts/bin/federation-join-registry.sh --token "$TOKEN" --site-env
  cd federation && SDS_ENV=production just up
  ./scripts/bin/federation-join-registry.sh --preflight --site-env

EOF
}

# shellcheck source=../lib/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../lib/common.sh"

SET_CHALLENGE="${FEDERATION_ROOT}/scripts/bin/set-registry-challenge.sh"
PREFLIGHT=0
TOKEN=""
CHALLENGE_ENV=""
PASS_ARGS=()

while [[ $# -gt 0 ]]; do
	case "$1" in
	--preflight)
		PREFLIGHT=1
		shift
		;;
	--token)
		TOKEN="${2:-}"
		PASS_ARGS+=("$1" "${2:-}")
		shift 2
		;;
	--env-file | --peer | --site-env)
		case "$1" in
		--env-file)
			CHALLENGE_ENV="${2:-}"
			PASS_ARGS+=("$1" "${2:-}")
			shift 2
			;;
		--peer)
			CHALLENGE_ENV="${FEDERATION_ROOT}/.env.peer"
			PASS_ARGS+=("$1")
			shift
			;;
		--site-env)
			CHALLENGE_ENV="${FEDERATION_ROOT}/site.env"
			PASS_ARGS+=("$1")
			shift
			;;
		esac
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

if [[ "${PREFLIGHT}" == "1" ]]; then
	[[ -n "${CHALLENGE_ENV}" ]] || CHALLENGE_ENV="${FEDERATION_ROOT}/site.env"
	export FEDERATION_DOCTOR_CHALLENGE_ENV="${CHALLENGE_ENV}"
	export FEDERATION_DOCTOR_REQUIRE_CHALLENGE=1
	exec "${FEDERATION_ROOT}/scripts/bin/federation-doctor.sh" preflight_apply
fi

if [[ -z "${TOKEN}" ]]; then
	echo "ERROR: --token is required (or use --preflight after recreating sync)" >&2
	usage
	exit 1
fi

if [[ ${#PASS_ARGS[@]} -eq 0 ]]; then
	echo "ERROR: specify --env-file, --peer, or --site-env" >&2
	usage
	exit 1
fi

"${SET_CHALLENGE}" "${PASS_ARGS[@]}"

case "${CHALLENGE_ENV}" in
*"site.env")
	PREFLIGHT_HINT="--site-env"
	;;
*"\.env\.peer")
	PREFLIGHT_HINT="--peer"
	;;
*)
	if [[ -n "${CHALLENGE_ENV}" ]]; then
		PREFLIGHT_HINT="--env-file ${CHALLENGE_ENV}"
	else
		PREFLIGHT_HINT="--site-env"
	fi
	;;
esac

echo ""
echo "After recreating sync, run preflight (includes registry_challenge check):"
echo "  cd ${FEDERATION_ROOT}"
echo "  ./scripts/bin/federation-join-registry.sh --preflight ${PREFLIGHT_HINT}"