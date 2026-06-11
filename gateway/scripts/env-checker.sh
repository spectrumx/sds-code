#!/usr/bin/env bash

# env-checker.sh — Audit all .env files against their example/template counterparts
# Usage: bash gateway/scripts/env-checker.sh   (or chmod +x and run directly)

set -Eeuo pipefail

# ─── Colors ────────────────────────────────────────────────────────────────────
ESC=$'\033'
COLOR_CYAN="${ESC}[36m"
COLOR_MAGENTA="${ESC}[35m"
COLOR_BOLD_CYAN="${ESC}[1;36m"
COLOR_WHITE="${ESC}[37m"
COLOR_GREEN="${ESC}[32m"
COLOR_YELLOW="${ESC}[33m"
COLOR_RED="${ESC}[31m"
COLOR_BOLD_YELLOW="${ESC}[1;33m"
COLOR_RESET="${ESC}[0m"

function log_debug() { printf "${COLOR_MAGENTA}❯❯❯ %s${COLOR_RESET}\n" "$*"; }
function log_info() { printf "${COLOR_WHITE}ℹ   %s${COLOR_RESET}\n" "$*"; }
function log_success() { printf "${COLOR_GREEN}✓   %s${COLOR_RESET}\n" "$*"; }
function log_warn() { printf "${COLOR_YELLOW}⚠ %s${COLOR_RESET}\n" "$*"; }
function log_error() { printf "${COLOR_RED}✗   %s${COLOR_RESET}\n" "$*"; }
function log_section() { printf "\n${COLOR_BOLD_CYAN}  %s${COLOR_RESET}\n\n" "$*"; }
function log_divider() { printf "\n${COLOR_BOLD_YELLOW}%s${COLOR_RESET}\n\n" "$*"; }

# ─── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SCRIPT_NAME="$(basename -- "${BASH_SOURCE[0]}")"
BASE_DIR="$(cd -- "$SCRIPT_DIR/../.envs" && pwd -P)" || {
	echo "ERROR: .envs directory not found at $SCRIPT_DIR/../.envs" >&2
	exit 1
}

# ─── Global counters ──────────────────────────────────────────────────────────
declare -g TOTAL_OK=0
declare -g TOTAL_MISSING=0
declare -g TOTAL_UNSET=0
declare -g TOTAL_UNRECOGNIZED=0
declare -g TOTAL_DEPRECATED=0

# Counters per service/env
declare -A COUNT_OK
declare -A COUNT_MISSING
declare -A COUNT_UNSET
declare -A COUNT_UNRECOGNIZED
declare -A COUNT_DEPRECATED

# Track whether actual env file exists
declare -A FILE_EXISTS

# Non-OK variable names per service/env (for tree detail view)
declare -A VARS_MISSING
declare -A VARS_UNSET
declare -A VARS_UNRECOGNIZED
declare -A VARS_DEPRECATED

# All service/env combos processed (for summary ordering)
declare -a SERVICE_ENV_ORDER=()

# ─── Helper: extract variables from an env file ────────────────────────────────
# Outputs lines: NAME=VALUE (one per active variable)
# Skips: comments, annotation lines, blank lines
# Annotation pattern: # WORD in WORD: value   (e.g., "# OPENSEARCH_USE_SSL in prod: true")
function extract_vars {
	local file="$1"
	[[ -f "$file" ]] || return 0

	while IFS= read -r line; do
		# Strip leading/trailing whitespace
		local trimmed
		trimmed="${line#"${line%%[![:space:]]*}"}"
		trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"

		# Skip blank lines
		[[ -z "$trimmed" ]] && continue

		# Skip comment-only lines
		[[ "$trimmed" == \#* ]] && continue

		# Parse: handle "export VAR=value", "VAR = value", and "VAR=value"
		local var_name var_value
		if [[ "$trimmed" =~ ^(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*(.*) ]]; then
			var_name="${BASH_REMATCH[2]}"
			var_value="${BASH_REMATCH[3]}"
			# Only accept uppercase + underscore variable names
			if [[ "$var_name" =~ ^[A-Z_][A-Z0-9_]*$ ]]; then
				# Trim trailing whitespace from value
				var_value="${var_value%"${var_value##*[![:space:]]}"}"
				printf '%s=%s\n' "$var_name" "$var_value"
			fi
		fi
	done <"$file"
}

# ─── Helper: extract commented-out variables from an env file ──────────────────
# Outputs lines: NAME (commented-out var names)
function extract_commented_vars {
	local file="$1"
	[[ -f "$file" ]] || return 0

	while IFS= read -r line; do
		local trimmed
		trimmed="${line#"${line%%[![:space:]]*}"}"
		trimmed="${trimmed%"${trimmed##*[![:space:]]}"}"

		[[ -z "$trimmed" ]] && continue

		# Must start with # (after optional whitespace)
		[[ "$trimmed" != \#* ]] && continue

		# Must NOT be an annotation line: # WORD in WORD: value
		# Annotation pattern check
		if [[ "$trimmed" =~ ^#[[:space:]]*[A-Z_][A-Z0-9_]*([[:space:]]*=[^[:space:]]*)?[[:space:]]+in[[:space:]]+ ]]; then
			continue
		fi

		# Skip format description lines: # VAR_NAME format: some description
		if [[ "$trimmed" =~ ^#[[:space:]]*[A-Z_][A-Z0-9_]*[[:space:]]+(format|description|example)[[:space:]]*: ]]; then
			continue
		fi

		# Must not start with emoji
		if [[ "$trimmed" =~ ^[🚨🔴⚠️💡] ]]; then
			continue
		fi

		# Extract variable name from commented line: # VAR = value or # VAR=value
		if [[ "$trimmed" =~ ^#[[:space:]]*([A-Z_][A-Z0-9_]*)[[:space:]]*= ]]; then
			local var_name="${BASH_REMATCH[1]}"
			printf '%s\n' "$var_name"
		fi
	done <"$file"
}

# ─── Check a single example file for a variable definition (non-commented) ─────
function var_in_example {
	local var_name="$1"
	local ex_file="$2"
	[[ -f "$ex_file" ]] || return 1
	grep -qE "^${var_name}[[:space:]]*=" "$ex_file" 2>/dev/null
}

# ─── Process one service ───────────────────────────────────────────────────────
# Args: service example_file local_actual production_actual
function process_service() {
	local service="$1"
	local example_file="$2"
	local local_actual="$3"
	local production_actual="$4"

	# Collect example files for this service (for UNRECOGNIZED check)
	SERVICE_EXAMPLE_FILES=()
	# The primary example file
	if [[ -f "$example_file" ]]; then
		SERVICE_EXAMPLE_FILES+=("$example_file")
	fi

	# Also check prod-example if it exists (for django/storage)
	local prod_example_file
	if [[ "$service" == "django" ]]; then
		prod_example_file="${BASE_DIR}/example/django.prod-example.env"
	elif [[ "$service" == "storage" ]]; then
		prod_example_file="${BASE_DIR}/example/storage.prod.env"
	fi

	if [[ -n "${prod_example_file:-}" && -f "$prod_example_file" ]]; then
		SERVICE_EXAMPLE_FILES+=("$prod_example_file")
	fi

	# ── Determine which env dirs exist ──
	local has_local=0 has_ci=0 has_production=0
	if [[ -d "${BASE_DIR}/local" ]]; then has_local=1; fi
	if [[ -d "${BASE_DIR}/ci" ]]; then has_ci=1; fi
	if [[ -d "${BASE_DIR}/production" ]]; then has_production=1; fi

	# ── Local env check ──
	if [[ $has_local -eq 1 ]]; then
		process_env "$service" "local" "$example_file" "$local_actual" 1
	fi

	# ── CI env check ──
	if [[ $has_ci -eq 1 ]]; then
		# Try to find CI example files (not all services have them)
		local ci_base
		ci_base="${BASE_DIR}/ci/$(basename "$example_file")"
		if [[ -f "$ci_base" ]]; then
			process_env "$service" "ci" "$example_file" "$ci_base" 2
		else
			# No CI example file — check if CI actual dir exists with files
			local ci_dir="${BASE_DIR}/ci"
			local ci_file_count
			ci_file_count=$(find "$ci_dir" -maxdepth 1 -name "*.env" -type f 2>/dev/null | wc -l)
			if [[ $ci_file_count -gt 0 ]]; then
				log_warn "  CI env files exist but no example template for '${service}'"
				# Still check actual CI file against available examples
				local ci_actual
				ci_actual="${ci_dir}/$(basename "$example_file")"
				if [[ -f "$ci_actual" ]]; then
					process_env "$service" "ci" "$example_file" "$ci_actual" 2
				fi
			fi
		fi
	fi

	# ── Production env check ──
	if [[ $has_production -eq 1 ]]; then
		process_env "$service" "production" "$example_file" "$production_actual" 0
	fi
}

# ─── Process one env for one service ───────────────────────────────────────────
function process_env() {
	local service="$1"
	local env_name="$2"
	local example_file="$3"
	local actual_file="$4"
	local is_local="$5"

	local key="${service}|${env_name}"
	SERVICE_ENV_ORDER+=("$key")

	local example_dir="" actual_dir=""
	if [[ "$is_local" -eq 1 ]]; then
		example_dir="example"
		actual_dir="local"
	elif [[ "$is_local" -eq 2 ]]; then
		example_dir="example"
		actual_dir="ci"
	else
		example_dir="example"
		actual_dir="production"
	fi

	local example_path
	example_path="${BASE_DIR}/${example_dir}/$(basename "$example_file")"
	local actual_path
	actual_path="${BASE_DIR}/${actual_dir}/$(basename "$actual_file")"

	# ── Track whether actual file exists ──
	local actual_file_exists=0
	[[ -f "$actual_path" ]] && actual_file_exists=1

	# ── Collect example variables (non-commented) ──
	declare -A example_vars=()
	while IFS= read -r vline; do
		[[ -z "$vline" ]] && continue
		example_vars["${vline%%=*}"]=1
	done < <(extract_vars "$example_path")

	# ── Collect commented-out vars from example ──
	declare -A example_commented=()
	if [[ -f "$example_path" ]]; then
		while IFS= read -r cvar; do
			[[ -z "$cvar" ]] && continue
			example_commented["$cvar"]=1
		done < <(extract_commented_vars "$example_path")
	fi

	# ── Collect actual variables ──
	declare -A actual_vars=()
	declare -A actual_values=()
	if [[ -f "$actual_path" ]]; then
		while IFS= read -r vline; do
			[[ -z "$vline" ]] && continue
			local aname avalue
			aname="${vline%%=*}"
			avalue="${vline#*=}"
			# Trim whitespace from name
			aname="${aname#"${aname%%[![:space:]]*}"}"
			aname="${aname%"${aname##*[![:space:]]}"}"
			# Trim trailing whitespace from value
			avalue="${avalue%"${avalue##*[![:space:]]}"}"
			actual_vars["$aname"]=1
			actual_values["$aname"]="$avalue"
		done < <(extract_vars "$actual_path")
	fi

	# ── Classify each variable ──
	local -a ok_list=()
	local -a missing_list=()
	local -a unset_list=()
	local -a unrecognized_list=()
	local -a deprecated_list=()

	# Check variables from actual file
	for var_name in "${!actual_vars[@]}"; do
		# DEPRECATED first: var in actual, commented-out in example
		if [[ -n "${example_commented[$var_name]:-}" ]]; then
			deprecated_list+=("$var_name")
			continue
		fi

		# UNRECOGNIZED: var not in any example file for this service
		local found_in_examples=0
		for ef in "${SERVICE_EXAMPLE_FILES[@]}"; do
			if var_in_example "$var_name" "$ef"; then
				found_in_examples=1
				break
			fi
		done
		if [[ $found_in_examples -eq 0 ]]; then
			unrecognized_list+=("$var_name")
			continue
		fi

		# Now check against the relevant example (the one mapped to this env)
		if ! var_in_example "$var_name" "$example_path"; then
			# Also check prod example files
			local found_any=0
			for ef in "${SERVICE_EXAMPLE_FILES[@]}"; do
				if [[ "$ef" != "$example_path" ]] && var_in_example "$var_name" "$ef"; then
					found_any=1
					break
				fi
			done
			if [[ $found_any -eq 0 ]]; then
				unrecognized_list+=("$var_name")
				continue
			fi
		fi

		# OK or UNSET
		local val="${actual_values[$var_name]:-}"
		local trimmed_val="${val#"${val%%[![:space:]]*}"}"
		trimmed_val="${trimmed_val%"${trimmed_val##*[![:space:]]}"}"
		if [[ -z "$trimmed_val" ]]; then
			unset_list+=("$var_name")
		else
			ok_list+=("$var_name")
		fi
	done

	# Check variables from example that are missing in actual
	for var_name in "${!example_vars[@]}"; do
		if [[ -z "${actual_vars[$var_name]:-}" ]]; then
			missing_list+=("$var_name")
		fi
	done

	# ── Store counts ──
	local count_ok=${#ok_list[@]}
	local count_missing=${#missing_list[@]}
	local count_unset=${#unset_list[@]}
	local count_unrecognized=${#unrecognized_list[@]}
	local count_deprecated=${#deprecated_list[@]}

	COUNT_OK["$key"]=$count_ok
	COUNT_MISSING["$key"]=$count_missing
	COUNT_UNSET["$key"]=$count_unset
	COUNT_UNRECOGNIZED["$key"]=$count_unrecognized
	COUNT_DEPRECATED["$key"]=$count_deprecated
	FILE_EXISTS["$key"]=$actual_file_exists

	# ── Store non-OK variable names for detail view ──
	VARS_MISSING["$key"]=$(printf '%s\n' "${missing_list[@]}" | sort | tr '\n' ' ')
	VARS_UNSET["$key"]=$(printf '%s\n' "${unset_list[@]}" | sort | tr '\n' ' ')
	VARS_UNRECOGNIZED["$key"]=$(printf '%s\n' "${unrecognized_list[@]}" | sort | tr '\n' ' ')
	VARS_DEPRECATED["$key"]=$(printf '%s\n' "${deprecated_list[@]}" | sort | tr '\n' ' ')

	# ── Update global counters ──
	TOTAL_OK=$((TOTAL_OK + count_ok))
	TOTAL_MISSING=$((TOTAL_MISSING + count_missing))
	TOTAL_UNSET=$((TOTAL_UNSET + count_unset))
	TOTAL_UNRECOGNIZED=$((TOTAL_UNRECOGNIZED + count_unrecognized))
	TOTAL_DEPRECATED=$((TOTAL_DEPRECATED + count_deprecated))

}

# ─── Summary ───────────────────────────────────────────────────────────────────
function print_summary() {
	# Determine overall result
	local has_errors=0 has_warnings=0
	[[ $TOTAL_MISSING -gt 0 || $TOTAL_UNRECOGNIZED -gt 0 ]] && has_errors=1
	[[ $TOTAL_UNSET -gt 0 || $TOTAL_DEPRECATED -gt 0 ]] && has_warnings=1

	local has_all=1
	if [[ $has_errors -eq 1 ]]; then
		has_all=0
	fi
	if [[ $has_warnings -eq 1 ]]; then
		has_all=0
	fi

	# Summary
	printf "${COLOR_BOLD_CYAN}────────────────────────────────────────────────${COLOR_RESET}\n"
	printf "${COLOR_BOLD_CYAN}  OVERALL SUMMARY${COLOR_RESET}\n"
	printf "${COLOR_BOLD_CYAN}────────────────────────────────────────────────${COLOR_RESET}\n"
	printf "  "

	printf "${COLOR_GREEN}%d OK${COLOR_RESET}, " "$TOTAL_OK"
	if [[ $TOTAL_MISSING -gt 0 ]]; then
		printf "${COLOR_RED}%d missing${COLOR_RESET}, " "$TOTAL_MISSING"
	else
		printf "%d missing, " "$TOTAL_MISSING"
	fi
	if [[ $TOTAL_UNSET -gt 0 ]]; then
		printf "${COLOR_CYAN}%d unset${COLOR_RESET}, " "$TOTAL_UNSET"
	else
		printf "%d unset, " "$TOTAL_UNSET"
	fi
	if [[ $TOTAL_UNRECOGNIZED -gt 0 ]]; then
		printf "${COLOR_RED}%d unrecognized${COLOR_RESET}, " "$TOTAL_UNRECOGNIZED"
	else
		printf "%d unrecognized, " "$TOTAL_UNRECOGNIZED"
	fi
	if [[ $TOTAL_DEPRECATED -gt 0 ]]; then
		printf "${COLOR_MAGENTA}%d deprecated${COLOR_RESET}" "$TOTAL_DEPRECATED"
	else
		printf "%d deprecated" "$TOTAL_DEPRECATED"
	fi
	printf "\n"

	# Result
	printf "  "
	if [[ $has_all -eq 1 ]]; then
		printf "${COLOR_GREEN}All checks passed ✅${COLOR_RESET}\n"
	elif [[ $has_errors -eq 1 ]]; then
		printf "${COLOR_RED}Errors found ❌${COLOR_RESET}\n"
	elif [[ $has_warnings -eq 1 ]]; then
		printf "${COLOR_YELLOW}Warnings found ⚠️${COLOR_RESET}\n"
	fi
	printf "\n"

	# Return exit code
	if [[ $has_errors -eq 1 ]]; then
		CHECKER_EXIT=2
	elif [[ $has_warnings -eq 1 ]]; then
		CHECKER_EXIT=1
	else
		CHECKER_EXIT=0
	fi
}

# ─── Tree Report ───────────────────────────────────────────────────────────────
function print_tree_report() {
	local envs=("local" "ci" "production")

	for env in "${envs[@]}"; do
		# Skip if env directory doesn't exist
		[[ ! -d "${BASE_DIR}/${env}" ]] && continue

		printf "${COLOR_BOLD_CYAN}── %s/ ──${COLOR_RESET}\n" "$env"

		# Collect keys for this environment (preserving order)
		local -a env_keys=()
		for key in "${SERVICE_ENV_ORDER[@]}"; do
			local key_env="${key##*|}"
			[[ "$key_env" == "$env" ]] && env_keys+=("$key")
		done

		local total_keys=${#env_keys[@]}
		local idx=0
		for key in "${env_keys[@]}"; do
			local svc="${key%%|*}"
			local prefix="├──"
			[[ $((idx + 1)) -eq $total_keys ]] && prefix="└──"

			local tree_prefix="$prefix"
			local detail_prefix="│   "
			[[ "$tree_prefix" == "└──" ]] && detail_prefix="    "

			local file_exists=${FILE_EXISTS["$key"]:-0}

			printf "%s %-18s" "$tree_prefix" "${svc}.env"

			if [[ $file_exists -eq 0 ]]; then
				printf "  ${COLOR_RED}🔴 FILE NOT FOUND${COLOR_RESET}\n"
			else
				local ok=${COUNT_OK["$key"]:-0}
				local missing=${COUNT_MISSING["$key"]:-0}
				local unset_c=${COUNT_UNSET["$key"]:-0}
				local unrecognized=${COUNT_UNRECOGNIZED["$key"]:-0}
				local deprecated=${COUNT_DEPRECATED["$key"]:-0}

				[[ $ok -gt 0 ]] && printf "  ${COLOR_GREEN}✅ OK: ${ok}${COLOR_RESET}"
				[[ $missing -gt 0 ]] && printf "  ${COLOR_YELLOW}⚠️ MISSING: ${missing}${COLOR_RESET}"
				[[ $unset_c -gt 0 ]] && printf "  ${COLOR_CYAN}⏺️ UNSET: ${unset_c}${COLOR_RESET}"
				[[ $unrecognized -gt 0 ]] && printf "  ${COLOR_RED}❓ UNRECOGNIZED: ${unrecognized}${COLOR_RESET}"
				[[ $deprecated -gt 0 ]] && printf "  ${COLOR_MAGENTA}🗑️ DEPRECATED: ${deprecated}${COLOR_RESET}"
				printf "\n"

				# Detail: one var per line, tree-nested under the file
				local total_vars=$((missing + unset_c + unrecognized + deprecated))
				local var_idx=0
				local var conn
				if [[ $missing -gt 0 ]]; then
					for var in ${VARS_MISSING[$key]}; do
						var_idx=$((var_idx + 1))
						conn="├──"
						[[ $var_idx -eq $total_vars ]] && conn="└──"
						printf "%s${conn} ${COLOR_YELLOW}⚠️  %s${COLOR_RESET}\n" "$detail_prefix" "$var"
					done
				fi
				if [[ $unset_c -gt 0 ]]; then
					for var in ${VARS_UNSET[$key]}; do
						var_idx=$((var_idx + 1))
						conn="├──"
						[[ $var_idx -eq $total_vars ]] && conn="└──"
						printf "%s${conn} ${COLOR_CYAN}⏺️  %s${COLOR_RESET}\n" "$detail_prefix" "$var"
					done
				fi
				if [[ $unrecognized -gt 0 ]]; then
					for var in ${VARS_UNRECOGNIZED[$key]}; do
						var_idx=$((var_idx + 1))
						conn="├──"
						[[ $var_idx -eq $total_vars ]] && conn="└──"
						printf "%s${conn} ${COLOR_RED}❓  %s${COLOR_RESET}\n" "$detail_prefix" "$var"
					done
				fi
				if [[ $deprecated -gt 0 ]]; then
					for var in ${VARS_DEPRECATED[$key]}; do
						var_idx=$((var_idx + 1))
						conn="├──"
						[[ $var_idx -eq $total_vars ]] && conn="└──"
						printf "%s${conn} ${COLOR_MAGENTA}🗑️  %s${COLOR_RESET}\n" "$detail_prefix" "$var"
					done
				fi
			fi

			idx=$((idx + 1))
		done

		printf "\n"
	done
}

# ─── Main ───────────────────────────────────────────────────────────────────────
function main() {
	CHECKER_EXIT=0

	log_section "🔍 Environment Variable Auditor"
	log_info "  Base directory: ${BASE_DIR}"
	log_info "  Script: ${SCRIPT_NAME}"
	printf "\n"

	# Detect which env dirs exist
	local detected_envs=""
	if [[ -d "${BASE_DIR}/local" ]]; then
		detected_envs="${detected_envs}local "
	fi
	if [[ -d "${BASE_DIR}/ci" ]]; then
		detected_envs="${detected_envs}ci "
	fi
	if [[ -d "${BASE_DIR}/production" ]]; then
		detected_envs="${detected_envs}production"
	fi

	log_info "  Detected env directories: ${detected_envs}"
	printf "\n"

	# ── OpenSearch ──
	process_service "opensearch" \
		"${BASE_DIR}/example/opensearch.env" \
		"${BASE_DIR}/local/opensearch.env" \
		"${BASE_DIR}/production/opensearch.env"

	# ── Django ──
	process_service "django" \
		"${BASE_DIR}/example/django.env" \
		"${BASE_DIR}/local/django.env" \
		"${BASE_DIR}/production/django.env"

	# ── Postgres ──
	process_service "postgres" \
		"${BASE_DIR}/example/postgres.env" \
		"${BASE_DIR}/local/postgres.env" \
		"${BASE_DIR}/production/postgres.env"

	# ── Storage ──
	process_service "storage" \
		"${BASE_DIR}/example/storage.env" \
		"${BASE_DIR}/local/storage.env" \
		"${BASE_DIR}/production/storage.env"

	# ── Summary ──
	print_tree_report
	print_summary

	# Exit with proper code based on audit results
	exit "$CHECKER_EXIT"
}

main "$@"
