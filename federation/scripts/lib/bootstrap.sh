#!/usr/bin/env bash
# Call after setting FEDERATION_ROOT (parent of scripts/). Exports env-selection targets.
federation_script_init() {
	: "${FEDERATION_ROOT:?FEDERATION_ROOT must be set before federation_script_init}"
	ENV_SELECTION="${FEDERATION_ROOT}/scripts/env-selection.sh"
	SDS_ENV_TYPE="$("${ENV_SELECTION}" env)"
	COMPOSE_FILE="$("${ENV_SELECTION}" compose_file)"
	SYNC_CONTAINER="$("${ENV_SELECTION}" sync_container)"
	export ENV_SELECTION SDS_ENV_TYPE COMPOSE_FILE SYNC_CONTAINER
	GATEWAY_ROOT="${FEDERATION_ROOT}/../gateway"
	export GATEWAY_ROOT
}
