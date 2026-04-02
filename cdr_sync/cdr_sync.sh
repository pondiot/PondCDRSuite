#!/bin/bash
# cdr_sync.sh - SFTP synchronization script using lftp
# Supports pull (download) and push (upload) operations

set -euo pipefail

# Script directory (for relative paths)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="${SCRIPT_DIR}/logs"

# Ensure logs directory exists
mkdir -p "${LOGS_DIR}"

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Global variables (set after config load)
CONFIG_NAME=""
LOG_FILE=""
JSON_LOG_FILE=""
LFTP_LOG_FILE=""
START_TIME=""

usage() {
    echo "Usage: $0 <pull|push> <config_file>"
    echo ""
    echo "Arguments:"
    echo "  pull         Download files from remote SFTP to local directory"
    echo "  push         Upload files from local directory to remote SFTP"
    echo "  config_file  Path to .env config file with connection settings"
    echo ""
    echo "Examples:"
    echo "  $0 pull configs/telna.env"
    echo "  $0 push configs/client_acme.env"
    exit 1
}

log_text() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp="$(date -u '+%Y-%m-%d %H:%M:%S GMT')"
    echo "${timestamp} - [${level}] ${message}" >> "${LOG_FILE}"

    # Also print to stdout with colors
    case "${level}" in
        INFO)  echo -e "${GREEN}[${level}]${NC} ${message}" ;;
        WARN)  echo -e "${YELLOW}[${level}]${NC} ${message}" ;;
        ERROR) echo -e "${RED}[${level}]${NC} ${message}" ;;
        *)     echo "[${level}] ${message}" ;;
    esac
}

log_json() {
    local status="$1"
    local message="$2"
    local error="${3:-}"
    local duration="${4:-0}"
    local files_count="${5:-0}"
    local timestamp
    timestamp="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

    # Escape special characters in strings for JSON
    message="${message//\\/\\\\}"
    message="${message//\"/\\\"}"
    message="${message//$'\n'/\\n}"
    error="${error//\\/\\\\}"
    error="${error//\"/\\\"}"
    error="${error//$'\n'/\\n}"

    echo "{\"timestamp\":\"${timestamp}\",\"config\":\"${CONFIG_NAME}\",\"operation\":\"${OPERATION}\",\"host\":\"${SFTP_HOST}\",\"status\":\"${status}\",\"message\":\"${message}\",\"error\":\"${error}\",\"duration_sec\":${duration},\"files_count\":${files_count}}" >> "${JSON_LOG_FILE}"
}

load_env_file() {
    local env_file="$1"
    if [[ ! -f "${env_file}" ]]; then
        echo -e "${RED}[ERROR]${NC} Config file not found: ${env_file}"
        exit 1
    fi

    # Source the env file, ignoring comments and empty lines
    set -a
    # shellcheck source=/dev/null
    source <(grep -v '^\s*#' "${env_file}" | grep -v '^\s*$')
    set +a
}

validate_config() {
    local missing=()

    [[ -z "${SFTP_HOST:-}" ]] && missing+=("SFTP_HOST")
    [[ -z "${SFTP_USER:-}" ]] && missing+=("SFTP_USER")
    [[ -z "${SFTP_PASSWORD:-}" ]] && missing+=("SFTP_PASSWORD")
    [[ -z "${REMOTE_DIR:-}" ]] && missing+=("REMOTE_DIR")
    [[ -z "${LOCAL_DIR:-}" ]] && missing+=("LOCAL_DIR")

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo -e "${RED}[ERROR]${NC} Missing required variables: ${missing[*]}"
        exit 1
    fi

    # Set defaults
    SFTP_PORT="${SFTP_PORT:-22}"
    TIMEOUT="${TIMEOUT:-300}"
    PARALLEL_TRANSFERS="${PARALLEL_TRANSFERS:-2}"
    DELETE_MISSING="${DELETE_MISSING:-false}"
}

send_alert() {
    local subject="$1"
    local message="$2"

    local send_telegram="${SEND_TELEGRAM:-false}"
    local send_email="${SEND_EMAIL:-false}"

    "${SCRIPT_DIR}/send_alert.py" \
        --subject "${subject}" \
        --message "${message}" \
        --telegram "${send_telegram}" \
        --email "${send_email}" || true
}

run_sync() {
    local mirror_cmd=""
    local delete_opt=""

    # Build delete option if enabled
    if [[ "${DELETE_MISSING,,}" == "true" ]]; then
        delete_opt="--delete"
    fi

    # Build mirror command based on operation
    if [[ "${OPERATION}" == "pull" ]]; then
        mirror_cmd="mirror --continue --verbose --no-perms ${delete_opt} \"${REMOTE_DIR}\" \"${LOCAL_DIR}\""
    else
        mirror_cmd="mirror --reverse --continue --verbose --no-perms ${delete_opt} \"${LOCAL_DIR}\" \"${REMOTE_DIR}\""
    fi

    # Create temporary lftp script
    local lftp_script
    lftp_script=$(mktemp)
    cleanup() { rm -f "${lftp_script:-}"; }
    trap cleanup RETURN

    cat > "${lftp_script}" << EOF
set net:timeout 30
set net:max-retries 5
set net:reconnect-interval-base 5
set net:reconnect-interval-multiplier 1.5
set cmd:fail-exit true
set mirror:parallel-transfer-count ${PARALLEL_TRANSFERS}
set mirror:use-pget-n 2
set ssl:verify-certificate no

open -u "${SFTP_USER}","${SFTP_PASSWORD}" -p ${SFTP_PORT} sftp://${SFTP_HOST}

${mirror_cmd}

bye
EOF

    # Ensure local directory exists for pull operations
    if [[ "${OPERATION}" == "pull" ]]; then
        mkdir -p "${LOCAL_DIR}"
    fi

    # Run lftp with timeout
    local rc=0
    local lftp_output
    lftp_output=$(timeout "${TIMEOUT}" lftp -f "${lftp_script}" 2>&1) || rc=$?

    # Only write lftp log if there's actual output
    if [[ -n "${lftp_output}" ]]; then
        echo "${lftp_output}" > "${LFTP_LOG_FILE}"
    fi

    return ${rc}
}

count_files() {
    local dir="$1"
    if [[ -d "${dir}" ]]; then
        find "${dir}" -type f 2>/dev/null | wc -l
    else
        echo "0"
    fi
}

extract_lftp_error() {
    # Extract last error message from lftp log
    if [[ -f "${LFTP_LOG_FILE}" ]]; then
        grep -i "error\|fail\|denied\|refused\|timeout" "${LFTP_LOG_FILE}" | tail -1 || echo "Unknown error"
    else
        echo "No lftp log available"
    fi
}

extract_transferred_files() {
    # Extract list of transferred files from lftp log
    if [[ ! -f "${LFTP_LOG_FILE}" ]]; then
        return
    fi

    # lftp verbose format: "get: filename (size)" or "put: filename (size)"
    grep -E "^(get|put):" "${LFTP_LOG_FILE}" | sed -E 's/^(get|put): //; s/ \(.*\)$//' | sort
}

main() {
    # Validate arguments
    if [[ $# -lt 2 ]]; then
        usage
    fi

    OPERATION="$1"
    local config_file="$2"

    # Validate operation
    if [[ "${OPERATION}" != "pull" && "${OPERATION}" != "push" ]]; then
        echo -e "${RED}[ERROR]${NC} Invalid operation: ${OPERATION}. Use 'pull' or 'push'."
        exit 1
    fi

    # Extract config name from path
    CONFIG_NAME="$(basename "${config_file}" .env)"

    # Setup log files
    local date_suffix
    date_suffix="$(date '+%Y%m%d')"
    LOG_FILE="${LOGS_DIR}/${CONFIG_NAME}_${date_suffix}.log"
    JSON_LOG_FILE="${LOGS_DIR}/${CONFIG_NAME}_${date_suffix}.json"
    LFTP_LOG_FILE="${LOGS_DIR}/${CONFIG_NAME}_lftp_${date_suffix}.log"

    # Load operation config
    load_env_file "${config_file}"
    validate_config

    # Set defaults for notification settings (can be overridden in client config)
    SEND_TELEGRAM="${SEND_TELEGRAM:-false}"
    SEND_EMAIL="${SEND_EMAIL:-false}"

    # Record start time
    START_TIME=$(date +%s)

    log_text "INFO" "Starting ${OPERATION} operation for ${CONFIG_NAME}"
    log_text "INFO" "Host: ${SFTP_HOST}, Remote: ${REMOTE_DIR}, Local: ${LOCAL_DIR}"

    # Run synchronization
    local rc=0
    run_sync || rc=$?

    # Calculate duration
    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - START_TIME))

    # Count files in target directory
    local target_dir="${LOCAL_DIR}"
    [[ "${OPERATION}" == "push" ]] && target_dir="${REMOTE_DIR}"
    local files_count
    files_count=$(count_files "${LOCAL_DIR}")

    # Handle result
    case ${rc} in
        0)
            log_text "INFO" "Sync completed successfully in ${duration}s"
            local transferred_files
            transferred_files=$(extract_transferred_files)
            if [[ -n "${transferred_files}" ]]; then
                local transferred_count
                transferred_count=$(echo "${transferred_files}" | wc -l)
                log_text "INFO" "Transferred ${transferred_count} file(s):"
                while IFS= read -r file; do
                    [[ -n "${file}" ]] && log_text "INFO" "  - ${file}"
                done <<< "${transferred_files}"
            else
                log_text "INFO" "No new files transferred"
            fi
            log_json "success" "Sync completed" "" "${duration}" "${files_count}"
            ;;
        124)
            local error_msg="Operation timed out after ${TIMEOUT}s"
            log_text "ERROR" "${error_msg}"
            log_json "timeout" "Operation timed out" "${error_msg}" "${duration}" "0"
            send_alert "CDR Sync Timeout: ${CONFIG_NAME}" "Operation: ${OPERATION}
Host: ${SFTP_HOST}
Timeout: ${TIMEOUT}s
Duration: ${duration}s"
            ;;
        *)
            local lftp_error
            lftp_error=$(extract_lftp_error)
            log_text "ERROR" "Sync failed (rc=${rc}): ${lftp_error}"
            log_json "failed" "Sync failed" "${lftp_error}" "${duration}" "0"
            send_alert "CDR Sync Failed: ${CONFIG_NAME}" "Operation: ${OPERATION}
Host: ${SFTP_HOST}
Exit code: ${rc}
Error: ${lftp_error}
Duration: ${duration}s"
            ;;
    esac

    exit ${rc}
}

main "$@"
