#!/usr/bin/env bash
# Declarative staging & VPS environment promotion pipeline with automated rollback (REQ-STAGE-001).
# Supports atomic release symlinks, pre-flight gate validation, health checks, and instant rollback.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_TARGET_ROOT="/opt/programming-desk"
RELEASE_ROOT="${DESK_RELEASES_ROOT:-/opt/programming-desk-releases}"
CURRENT_LINK="${DESK_CURRENT_LINK:-$DEFAULT_TARGET_ROOT}"
UNIT="${DESK_SERVICE_UNIT:-desk-gateway.service}"
GATEWAY_URL="${DESK_HEALTH_URL:-http://127.0.0.1:8791/healthz}"
MAX_HEALTH_ATTEMPTS="${DESK_HEALTH_ATTEMPTS:-15}"
HEALTH_INTERVAL="${DESK_HEALTH_INTERVAL:-1}"

log() {
  printf '[deploy-staging %s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

err() {
  printf '[deploy-staging %s] ERROR: %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >&2
}

# 1. Validation & Pre-flight
SRC_DIR="${1:-}"
if [[ -z "$SRC_DIR" ]]; then
  echo "Usage: $0 <source-directory> [release-id]" >&2
  exit 1
fi

SRC_DIR="$(cd "$SRC_DIR" && pwd)"
RELEASE_ID="${2:-$(date -u +'%Y%m%d%H%M%S')-$(git -C "$SRC_DIR" rev-parse --short HEAD 2>/dev/null || echo 'manual')}"
TARGET_RELEASE="$RELEASE_ROOT/$RELEASE_ID"

log "Starting deployment for release: $RELEASE_ID"
log "Source directory: $SRC_DIR"
log "Target release directory: $TARGET_RELEASE"

# Record previous active release for atomic rollback
PREV_RELEASE=""
if [[ -L "$CURRENT_LINK" ]]; then
  PREV_RELEASE="$(readlink -f "$CURRENT_LINK" || true)"
elif [[ -d "$CURRENT_LINK" ]]; then
  PREV_RELEASE="$CURRENT_LINK.previous"
fi

rollback() {
  local exit_code=$?
  err "Deployment failure detected (exit code: $exit_code). Initiating automated rollback..."
  if [[ -n "$PREV_RELEASE" && -d "$PREV_RELEASE" ]]; then
    log "Rolling back symlink $CURRENT_LINK -> $PREV_RELEASE"
    ln -sfn "$PREV_RELEASE" "$CURRENT_LINK"
    if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet "$UNIT" 2>/dev/null; then
      log "Restarting $UNIT to previous release..."
      systemctl restart "$UNIT" || err "Failed to restart unit during rollback"
    fi
  else
    err "No previous valid release found to roll back to!"
  fi
  # Clean up failed candidate directory
  if [[ -d "$TARGET_RELEASE" ]]; then
    rm -rf "$TARGET_RELEASE"
  fi
  err "Rollback complete. Deployment failed."
  exit "$exit_code"
}

trap rollback ERR

# 2. Pre-deployment quality & ownership verification
log "Running pre-flight quality checks in source tree..."
if [[ -f "$SRC_DIR/ci/gates/check_ownership.py" ]]; then
  if ! python3 "$SRC_DIR/ci/gates/check_ownership.py" --validate-manifest; then
    err "Ownership manifest validation failed"
    false
  fi
fi

if [[ -f "$SRC_DIR/ci/gates/check_desk_integrity.py" ]]; then
  if ! python3 "$SRC_DIR/ci/gates/check_desk_integrity.py" --repo "$SRC_DIR"; then
    err "Desk integrity check failed"
    false
  fi
fi

# 3. Materialize candidate release directory
mkdir -p "$RELEASE_ROOT"
mkdir -p "$TARGET_RELEASE"

log "Copying application tree to target release $TARGET_RELEASE..."
if command -v rsync >/dev/null 2>&1; then
  rsync -a --exclude '.venv/' --exclude '__pycache__/' --exclude '.git/' "$SRC_DIR/" "$TARGET_RELEASE/"
else
  cp -a "$SRC_DIR"/. "$TARGET_RELEASE"/
  rm -rf "$TARGET_RELEASE/.venv" "$TARGET_RELEASE/.git" 2>/dev/null || true
fi

# Sync dependencies if uv is available and pyproject.toml exists
UV_BIN="$(command -v uv 2>/dev/null || echo '/root/.local/bin/uv')"
if [[ -x "$UV_BIN" && -f "$TARGET_RELEASE/services/desk-gateway/pyproject.toml" ]]; then
  log "Syncing python virtualenv via uv in $TARGET_RELEASE/services/desk-gateway..."
  (cd "$TARGET_RELEASE/services/desk-gateway" && "$UV_BIN" sync)
fi

# 4. Atomic symlink swap
log "Executing atomic symlink cutover: $CURRENT_LINK -> $TARGET_RELEASE"
ln -sfn "$TARGET_RELEASE" "$CURRENT_LINK"

# 5. Service reload / restart
if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files "$UNIT" >/dev/null 2>&1; then
  log "Restarting systemd service $UNIT..."
  systemctl daemon-reload
  systemctl restart "$UNIT"
fi

# 6. Post-deployment health verification probe
CHECK_HEALTH="${DESK_CHECK_HEALTH:-true}"
if [[ "$CHECK_HEALTH" == "true" ]]; then
  log "Verifying gateway health at $GATEWAY_URL (max attempts: $MAX_HEALTH_ATTEMPTS)..."
  HEALTHY=false
  for ((i=1; i<=MAX_HEALTH_ATTEMPTS; i++)); do
    if command -v curl >/dev/null 2>&1; then
      HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$GATEWAY_URL" || true)"
      if [[ "$HTTP_CODE" == "200" ]]; then
        HEALTHY=true
        break
      fi
    else
      HEALTHY=true
      break
    fi
    log "Health check attempt $i/$MAX_HEALTH_ATTEMPTS returned $HTTP_CODE; retrying in ${HEALTH_INTERVAL}s..."
    sleep "$HEALTH_INTERVAL"
  done

  if [[ "$HEALTHY" != "true" ]]; then
    err "Health check probe failed after $MAX_HEALTH_ATTEMPTS attempts."
    exit 4
  fi
else
  log "Post-deployment health check skipped (DESK_CHECK_HEALTH=$CHECK_HEALTH)"
fi

# 7. Success - clear trap
trap - ERR
log "Deployment of release $RELEASE_ID verified successfully!"

# Prune older releases, keeping latest 5
if [[ -d "$RELEASE_ROOT" ]]; then
  log "Pruning old releases (retaining last 5)..."
  (cd "$RELEASE_ROOT" && ls -dt */ 2>/dev/null | tail -n +6 | xargs rm -rf 2>/dev/null || true)
fi

exit 0
