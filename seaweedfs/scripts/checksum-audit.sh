#!/usr/bin/env bash
# =============================================================================
# minio-checksum-audit.sh
#
# Randomly samples objects from a MinIO bucket and verifies that each object's
# BLAKE3 checksum matches its base name (the base name IS the expected hash).
#
# Usage:
#   checksum-audit.sh --bucket my_bucket
#   MC_ALIAS=my_minio MC_BUCKET=my_bucket checksum-audit.sh
#
# Environment variables:
#   MC_ALIAS      MinIO alias configured in `mc` (default: local)
#   MC_BUCKET     Bucket to audit (required)
#   MC_PREFIX     Optional key prefix to scope the scan, no leading slash (default: "files")
#   SAMPLE_RATE   Percentage of objects to sample, supports decimals (default: 1)
#   LOG_FILE      Path to the log file (default: ./checksum_audit.log)
#   FAIL_FAST     Exit on first mismatch if "true", otherwise audit all samples
#                 and exit with an error at the end (default: true)
# =============================================================================
set -Eeuo pipefail
IFS=$'\n\t'

MC_ALIAS="${MC_ALIAS:-local}"
MC_BUCKET="${MC_BUCKET:-}"
MC_PREFIX="${MC_PREFIX:-files}"
SAMPLE_RATE="${SAMPLE_RATE:-1}"
LOG_FILE="${LOG_FILE:-./checksum_audit.log}"
FAIL_FAST="${FAIL_FAST:-true}"
OBJECT_REGEX=".*/[0-9a-f]{64}(_.*)?$"
FIND_PATH=""

target=""
sampled=0
checked=0
errors=0
temp_files=()

color_reset=""
color_info=""
color_warn=""
color_error=""
color_fatal=""

function init_colors() {
    if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
        color_reset=$'\033[0m'
        color_info=$'\033[36m'
        color_warn=$'\033[33m'
        color_error=$'\033[31m'
        color_fatal=$'\033[35m'
    fi
}

function log() {
    local level="${1}"
    local color="${2}"
    local stream="${3}"
    shift 3
    local text="$*"
    local timestamp
    local message
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    message="[${timestamp}] [${level}] ${text}"

    printf '%s\n' "${message}" >>"${LOG_FILE}"

    if [[ "${stream}" == "stderr" ]]; then
        if [[ -n "${color}" ]]; then
            printf '%b%s%b\n' "${color}" "${message}" "${color_reset}" >&2
        else
            printf '%s\n' "${message}" >&2
        fi
        return
    fi

    if [[ -n "${color}" ]]; then
        printf '%b%s%b\n' "${color}" "${message}" "${color_reset}"
    else
        printf '%s\n' "${message}"
    fi
}

function log_info() {
    log "INFO" "${color_info}" "stdout" "$*"
}

function log_warn() {
    log "WARN" "${color_warn}" "stderr" "$*"
}

function log_error() {
    log "ERROR" "${color_error}" "stderr" "$*"
}

function log_fatal() {
    log "FATAL" "${color_fatal}" "stderr" "$*"
}

function die() {
    log_fatal "$*"
    exit 1
}

function remember_temp_file() {
    local file_path="${1}"
    temp_files+=("${file_path}")
}

function cleanup_temp_files() {
    local file_path=""
    for file_path in "${temp_files[@]-}"; do
        [[ -n "${file_path}" && -f "${file_path}" ]] || continue
        rm -f "${file_path}" || true
    done
}

function print_usage() {
    cat <<EOF
Usage:
  checksum-audit.sh [options]

Options:
  -a, --alias <name>        MinIO alias configured in mc (default: env MC_ALIAS or "local")
  -b, --bucket <name>       Bucket to audit (required; env fallback: MC_BUCKET)
  -p, --prefix <prefix>     Optional key prefix to scope the scan, no leading slash (default: env MC_PREFIX or "files")
  -r, --sample-rate <pct>   Sampling percentage in (0,100] (default: env SAMPLE_RATE or "1")
  -l, --log-file <path>     Log file path (default: env LOG_FILE or "./checksum_audit.log")
  -f, --fail-fast <bool>    true|false (default: env FAIL_FAST or "true")
      --no-fail-fast        Shortcut for --fail-fast false
  -h, --help                Show this help and exit

Examples:
  checksum-audit.sh --bucket spectrumx
  checksum-audit.sh -b spectrumx -r 0.5 --fail-fast false
  MC_BUCKET=spectrumx checksum-audit.sh -r 5
EOF
}

function parse_args() {
    while [[ $# -gt 0 ]]; do
        case "${1}" in
            -h|--help)
                print_usage
                exit 0
                ;;
            -a|--alias)
                [[ $# -lt 2 ]] && die "Missing value for ${1}"
                MC_ALIAS="${2}"
                shift 2
                ;;
            -b|--bucket)
                [[ $# -lt 2 ]] && die "Missing value for ${1}"
                MC_BUCKET="${2}"
                shift 2
                ;;
            -p|--prefix)
                [[ $# -lt 2 ]] && die "Missing value for ${1}"
                MC_PREFIX="${2}"
                shift 2
                ;;
            -r|--sample-rate)
                [[ $# -lt 2 ]] && die "Missing value for ${1}"
                SAMPLE_RATE="${2}"
                shift 2
                ;;
            -l|--log-file)
                [[ $# -lt 2 ]] && die "Missing value for ${1}"
                LOG_FILE="${2}"
                shift 2
                ;;
            -f|--fail-fast)
                [[ $# -lt 2 ]] && die "Missing value for ${1}"
                FAIL_FAST="${2}"
                shift 2
                ;;
            --no-fail-fast)
                FAIL_FAST="false"
                shift
                ;;
            --)
                shift
                break
                ;;
            -*)
                die "Unknown option: ${1}. Use --help for usage."
                ;;
            *)
                die "Unexpected positional argument: ${1}. Use --help for usage."
                ;;
        esac
    done

    if [[ $# -gt 0 ]]; then
        die "Unexpected positional argument: ${1}. Use --help for usage."
    fi
}

function require_commands() {
    for cmd in mc b3sum awk date jq mktemp; do
        command -v "${cmd}" >/dev/null 2>&1 || die "Required command not found: '${cmd}'"
    done
}

function validate_sample_rate() {
    if ! awk -v rate="${SAMPLE_RATE}" 'BEGIN { exit !(rate > 0 && rate <= 100) }'; then
        die "SAMPLE_RATE must be a number between 0 (exclusive) and 100. Got: '${SAMPLE_RATE}'"
    fi
    if ! mc alias list "${MC_ALIAS}" >/dev/null 2>&1; then
        log_error "Available MinIO aliases:"
        mc alias list
        die "MinIO alias '${MC_ALIAS}' not found in 'mc' configuration. Pass it with --alias or set MC_ALIAS environment variable."
    fi
}

function validate_fail_fast() {
    case "${FAIL_FAST}" in
        true|false) ;;
        *) die "FAIL_FAST must be 'true' or 'false'. Got: '${FAIL_FAST}'" ;;
    esac
}

function validate_config() {
    [[ -z "${MC_BUCKET}" ]] && die "MC_BUCKET must be set, or specified with --bucket <name>"
    validate_sample_rate
    validate_fail_fast
}

function set_target() {
    target="${MC_ALIAS}/${MC_BUCKET}"
}

function build_find_path() {
    local normalized_prefix="${MC_PREFIX#/}"
    normalized_prefix="${normalized_prefix%/}"

    if [[ -z "${normalized_prefix}" ]]; then
        FIND_PATH=""
        return
    fi

    FIND_PATH="${normalized_prefix}/*"
}

function is_fail_fast() {
    [[ "${FAIL_FAST}" == "true" ]]
}

function print_start_banner() {
    log_info "════════════════════════════════════════"
    log_info "MinIO BLAKE3 Checksum Audit — Starting"
    log_info "Target    : ${target}"
    log_info "Sample    : ${SAMPLE_RATE}%"
    log_info "Fail-fast : ${FAIL_FAST}"
    log_info "Prefix    : ${MC_PREFIX}"
    log_info "Path      : ${FIND_PATH:-<none>}"
    log_info "Regex     : ${OBJECT_REGEX}"
    log_info "Log file  : ${LOG_FILE}"
    log_info "════════════════════════════════════════"
}

function count_lines() {
    local input_file="${1}"
    awk 'END { print NR + 0 }' "${input_file}"
}

function filtered_objects() {
    local output_file="${1}"
    if [[ -n "${FIND_PATH}" ]]; then
        log_info "mc find \"${target}\" --path \"${FIND_PATH}\" --regex \"${OBJECT_REGEX}\" > ${output_file}"
        mc find "${target}" --path "${FIND_PATH}" --regex "${OBJECT_REGEX}" 2>>"${LOG_FILE}" >"${output_file}"
        return
    fi

    log_info "mc find \"${target}\" --regex \"${OBJECT_REGEX}\" > ${output_file}"
    mc find "${target}" --regex "${OBJECT_REGEX}" 2>>"${LOG_FILE}" >"${output_file}"
}

function sampled_objects() {
    local filtered_file="${1}"
    local sampled_file="${2}"

    awk \
        -v rate="${SAMPLE_RATE}" \
        -v seed="$(( $$ + $(date +%s) ))" \
        'BEGIN { srand(seed) } rand() * 100 < rate { print }' \
        "${filtered_file}" >"${sampled_file}"
}

function stream_hash() {
    local object_path="${1}"
    mc cat "${object_path}" 2>>"${LOG_FILE}" | b3sum --no-names 2>>"${LOG_FILE}"
}

function on_stream_failure() {
    local object_path="${1}"
    log_error "STREAM_FAIL — could not read or hash object: ${object_path}"
    errors=$((errors + 1))
    if is_fail_fast; then
        log_error "Aborting early (FAIL_FAST=true)."
        exit 1
    fi
}

function on_mismatch() {
    local object_path="${1}"
    local expected_hash="${2}"
    local actual_hash="${3}"
    log_error "MISMATCH — object  : ${object_path}"
    log_error "MISMATCH — expected: ${expected_hash}"
    log_error "MISMATCH — actual  : ${actual_hash}"
    errors=$((errors + 1))
    if is_fail_fast; then
        log_error "Aborting early (FAIL_FAST=true)."
        exit 1
    fi
}

function verify_object() {
    local object_path="${1}"
    local base_name="${object_path##*/}"
    local expected_hash="${base_name%%_*}"
    local actual_hash=""

    sampled=$((sampled + 1))
    # log_info "Verifying [#${sampled}]: ${object_path}"

    if ! actual_hash="$(stream_hash "${object_path}")"; then
        on_stream_failure "${object_path}"
        return
    fi

    checked=$((checked + 1))

    if [[ "${actual_hash}" != "${expected_hash}" ]]; then
        on_mismatch "${object_path}" "${expected_hash}" "${actual_hash}"
        return
    fi

    log_info "OK — ${object_path}"
}

function verify_objects_from_file() {
    local sampled_file="${1}"
    while IFS= read -r object_path; do
        verify_object "${object_path}"
    done <"${sampled_file}"
}

function audit_objects() {
    local filtered_file=""
    local sampled_file=""
    local filtered_count=0
    local sampled_count=0

    filtered_file="$(mktemp)"
    remember_temp_file "${filtered_file}"
    sampled_file="$(mktemp)"
    remember_temp_file "${sampled_file}"

    log_info "Running regex filter with: ${OBJECT_REGEX}"
    filtered_objects "${filtered_file}"
    filtered_count="$(count_lines "${filtered_file}")"
    log_info "Objects after regex filter: ${filtered_count}"

    if (( filtered_count == 0 )); then
        log_warn "No objects matched the regex filter. Skipping verification stage."
        return
    fi

    sampled_objects "${filtered_file}" "${sampled_file}"
    sampled_count="$(count_lines "${sampled_file}")"
    log_info "Objects after sampling: ${sampled_count}"

    if (( sampled_count == 0 )); then
        log_warn "No objects remained after sampling. Skipping verification stage."
        return
    fi

    verify_objects_from_file "${sampled_file}"
}

function print_summary() {
    local stream_errors=$((sampled - checked))

    log_info "════════════════════════════════════════"
    log_info "Audit Complete"
    log_info "Sampled       : ${sampled}"
    log_info "Hashed        : ${checked}"
    log_info "Stream errors : ${stream_errors}"
    log_info "Mismatches    : ${errors}"
    log_info "════════════════════════════════════════"
}

function finalize_result() {
    if [[ $sampled -eq 0 ]]; then
        log_warn "No objects were sampled. Bucket may be empty or prefix too narrow."
        log_info "Total objects in bucket ${MC_BUCKET}:"
        mc stat "${MC_ALIAS}/${MC_BUCKET}" --json 2>>"${LOG_FILE}" | \
            jq '.Usage.objectsCount' 2>>"${LOG_FILE}" || \
            log_warn "Could not retrieve object count for bucket."
        exit 0
    fi

    if [[ ${errors} -gt 0 ]]; then
        log_error "Audit FAILED — ${errors} error(s) detected across ${checked} verified objects."
        exit 1
    fi

    log_info "Audit PASSED — all ${checked} sampled objects are clean."
    exit 0
}

function main() {
    trap cleanup_temp_files EXIT INT TERM
    init_colors
    parse_args "$@"
    require_commands
    validate_config
    set_target
    build_find_path
    print_start_banner
    audit_objects
    print_summary
    finalize_result
}

main "$@"
