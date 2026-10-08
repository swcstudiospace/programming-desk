#!/usr/bin/env bash
# Zero-downtime hot reload for the desk gateway behind nginx (REQ-STAGE-002).
# Reloads DESK_SERVICE_UNIT via systemctl, or an explicit DESK_GATEWAY_PID_FILE
# when systemctl is absent. Never selects a process by command-line pattern.
set -euo pipefail

# Bash implements kill as a builtin, which ignores PATH. Disable it so a test
# can place a recorder named kill on PATH, and a host runs the external kill.
enable -n kill

UNIT="${DESK_SERVICE_UNIT:-desk-gateway.service}"
READY_URL="${DESK_READY_URL:-http://127.0.0.1:8791/readyz}"
NGINX_PID_FILE="${NGINX_PID_FILE:-/run/nginx.pid}"
RELOAD_TIMEOUT="${DESK_RELOAD_TIMEOUT:-15}"
NGINX_BIN="${NGINX_BIN:-nginx}"
SYSTEMCTL_BIN="${SYSTEMCTL_BIN:-systemctl}"
DESK_GATEWAY_PID_FILE="${DESK_GATEWAY_PID_FILE:-}"
DESK_RELOAD_NGINX="${DESK_RELOAD_NGINX:-false}"
DESK_RELOAD_DRY_RUN="${DESK_RELOAD_DRY_RUN:-0}"

log() {
  printf '[reload-nginx-gateway %s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

err() {
  printf '[reload-nginx-gateway %s] ERROR: %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >&2
}

is_truthy() {
  case "$1" in
    1|true|TRUE|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}

dry_run() {
  is_truthy "$DESK_RELOAD_DRY_RUN"
}

quote_cmd() {
  local rendered
  printf -v rendered '%q ' "$@"
  printf '%s' "${rendered% }"
}

run_or_print() {
  if dry_run; then
    log "DRY-RUN: $(quote_cmd "$@")"
    return 0
  fi
  "$@"
}

read_single_pid() {
  local file="$1"
  local label="$2"
  local raw pid
  if [[ ! -f "$file" ]]; then
    err "${label} is set but not a file: ${file}"
    exit 1
  fi
  IFS= read -r raw < "$file" || raw=""
  if [[ ! "$raw" =~ ^[[:space:]]*[0-9]+[[:space:]]*$ ]]; then
    err "${label} does not contain a single numeric PID: ${file}"
    exit 1
  fi
  pid="${raw//[[:space:]]/}"
  printf '%s' "$pid"
}

reload_gateway() {
  if command -v "$SYSTEMCTL_BIN" >/dev/null 2>&1; then
    log "Executing ${SYSTEMCTL_BIN} reload-or-restart on ${UNIT}..."
    if ! run_or_print "$SYSTEMCTL_BIN" reload-or-restart "$UNIT"; then
      err "${SYSTEMCTL_BIN} reload-or-restart ${UNIT} failed. Refusing to signal any process matched by pattern."
      exit 1
    fi
    return 0
  fi

  if [[ -n "$DESK_GATEWAY_PID_FILE" ]]; then
    local pid
    pid="$(read_single_pid "$DESK_GATEWAY_PID_FILE" "DESK_GATEWAY_PID_FILE")"
    log "Sending SIGHUP to gateway PID ${pid} from ${DESK_GATEWAY_PID_FILE}..."
    if ! run_or_print kill -HUP "$pid"; then
      err "kill -HUP ${pid} failed"
      exit 1
    fi
    return 0
  fi

  err "Cannot reload gateway: ${SYSTEMCTL_BIN} is not available and DESK_GATEWAY_PID_FILE is unset. Refusing to signal any process matched by pattern."
  exit 1
}

reload_nginx() {
  if ! is_truthy "$DESK_RELOAD_NGINX"; then
    log "Nginx reload skipped (DESK_RELOAD_NGINX=${DESK_RELOAD_NGINX})"
    return 0
  fi

  if ! command -v "$NGINX_BIN" >/dev/null 2>&1; then
    err "DESK_RELOAD_NGINX is set but ${NGINX_BIN} was not found"
    exit 1
  fi

  log "Validating nginx syntax..."
  if ! run_or_print "$NGINX_BIN" -t; then
    err "${NGINX_BIN} -t failed"
    exit 1
  fi

  if command -v "$SYSTEMCTL_BIN" >/dev/null 2>&1; then
    if dry_run; then
      log "DRY-RUN: $(quote_cmd "$SYSTEMCTL_BIN" is-active --quiet nginx)"
      log "DRY-RUN: $(quote_cmd "$SYSTEMCTL_BIN" reload nginx)"
      return 0
    fi
    if "$SYSTEMCTL_BIN" is-active --quiet nginx 2>/dev/null; then
      log "Reloading nginx via ${SYSTEMCTL_BIN} reload nginx..."
      "$SYSTEMCTL_BIN" reload nginx
      return 0
    fi
  elif dry_run; then
    log "DRY-RUN: ${SYSTEMCTL_BIN} is not available"
  fi

  if [[ -f "$NGINX_PID_FILE" ]]; then
    local nginx_pid
    nginx_pid="$(read_single_pid "$NGINX_PID_FILE" "NGINX_PID_FILE")"
    log "Sending SIGHUP to nginx PID ${nginx_pid} from ${NGINX_PID_FILE}..."
    if ! run_or_print kill -HUP "$nginx_pid"; then
      err "kill -HUP ${nginx_pid} failed"
      exit 1
    fi
    return 0
  fi

  err "DESK_RELOAD_NGINX is set but nginx is not an active ${SYSTEMCTL_BIN} unit and ${NGINX_PID_FILE} is missing"
  exit 1
}

await_ready() {
  local check_health="${DESK_CHECK_HEALTH:-true}"
  if ! is_truthy "$check_health"; then
    log "Readiness check skipped (DESK_CHECK_HEALTH=${check_health})"
    return 0
  fi

  if dry_run; then
    log "DRY-RUN: $(quote_cmd curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$READY_URL")"
    log "DRY-RUN: readiness check skipped"
    return 0
  fi

  log "Awaiting readiness at ${READY_URL}..."
  local is_ready="false"
  local i http_code
  for ((i=1; i<=RELOAD_TIMEOUT; i++)); do
    if command -v curl >/dev/null 2>&1; then
      HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "$READY_URL" || true)"
      http_code="$HTTP_CODE"
      if [[ "$http_code" == "200" ]]; then
        is_ready="true"
        break
      fi
    else
      is_ready="true"
      break
    fi
    sleep 1
  done

  if [[ "$is_ready" != "true" ]]; then
    err "Desk gateway failed to report ready at ${READY_URL} within ${RELOAD_TIMEOUT}s"
    exit 1
  fi
  log "Gateway reports ready."
}

log "Initiating zero-downtime hot reload..."
reload_gateway
await_ready
reload_nginx
log "Zero-downtime hot reload completed successfully."
exit 0
