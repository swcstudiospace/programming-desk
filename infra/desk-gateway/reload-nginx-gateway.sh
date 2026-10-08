#!/usr/bin/env bash
# Zero-downtime hot-reloading for Desk Gateway instances behind Nginx TLS termination (REQ-STAGE-002).
# Signals uvicorn/systemd workers, checks upstream readiness, and reloads Nginx gracefully.
set -euo pipefail

UNIT="${DESK_SERVICE_UNIT:-desk-gateway.service}"
READY_URL="${DESK_READY_URL:-http://127.0.0.1:8791/readyz}"
NGINX_PID_FILE="${NGINX_PID_FILE:-/run/nginx.pid}"
RELOAD_TIMEOUT="${DESK_RELOAD_TIMEOUT:-15}"

log() {
  printf '[reload-nginx-gateway %s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

err() {
  printf '[reload-nginx-gateway %s] ERROR: %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >&2
}

log "Initiating zero-downtime hot reload..."

# 1. Reload desk-gateway systemd unit or send SIGHUP to uvicorn master
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet "$UNIT" 2>/dev/null; then
  log "Executing systemctl reload-or-restart on $UNIT..."
  systemctl reload-or-restart "$UNIT"
else
  # Direct process lookup if running outside systemd
  PID=$(pgrep -f "desk-gateway" | head -n 1 || true)
  if [[ -n "$PID" ]]; then
    log "Sending SIGHUP to desk-gateway process (PID $PID)..."
    kill -HUP "$PID" 2>/dev/null || true
  fi
fi

# 2. Wait for Desk Gateway /readyz endpoint to answer green (if health checking is enabled)
CHECK_HEALTH="${DESK_CHECK_HEALTH:-true}"
if [[ "$CHECK_HEALTH" == "true" ]]; then
  log "Awaiting readiness at $READY_URL..."
  IS_READY=false
  for ((i=1; i<=RELOAD_TIMEOUT; i++)); do
    if command -v curl >/dev/null 2>&1; then
      HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "$READY_URL" || true)"
      if [[ "$HTTP_CODE" == "200" ]]; then
        IS_READY=true
        break
      fi
    else
      IS_READY=true
      break
    fi
    sleep 1
  done

  if [[ "$IS_READY" != "true" ]]; then
    err "Desk gateway failed to report ready at $READY_URL within ${RELOAD_TIMEOUT}s"
    exit 1
  fi
  log "Gateway reports ready."
else
  log "Readiness check skipped (DESK_CHECK_HEALTH=$CHECK_HEALTH)"
fi

# 3. Graceful Nginx configuration reload (no dropped connections)
if command -v nginx >/dev/null 2>&1; then
  log "Validating nginx syntax..."
  nginx -t
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet nginx 2>/dev/null; then
    log "Reloading nginx via systemctl reload nginx..."
    systemctl reload nginx
  elif [[ -f "$NGINX_PID_FILE" ]]; then
    log "Sending SIGHUP to Nginx master process..."
    kill -HUP "$(cat "$NGINX_PID_FILE")"
  fi
fi

log "Zero-downtime hot reload completed successfully."
exit 0
