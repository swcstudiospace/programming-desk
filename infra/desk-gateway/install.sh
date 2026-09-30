#!/usr/bin/env bash
# Install or update the desk-gateway systemd service on the VPS. Safe to rerun.
# Does not touch nginx, DNS or certificates — that is install-nginx.sh.
#
# Layout (Greptile P1 4141126594 / tip fixes incl. 4141252895, 4141252905):
# Canonical desk checkout is /opt/programming-desk so a future DESK_GATE_USER can
# traverse the tree and run ci/gates. Do NOT set DESK_GATE_USER in the live env
# until that drop is verified separately.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "install.sh: must run as root" >&2; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Repo root of the tree this script was invoked from (may be legacy /root/... or /opt/...).
SRC_ROOT="$(cd "$HERE/../.." && pwd)"
GATEWAY_ROOT=/opt/programming-desk
OLD_ROOT=/root/src/repos/programming-desk
GATEWAY_DIR="$GATEWAY_ROOT/services/desk-gateway"
ENV_DIR=/etc/desk-gateway
ENV_FILE="$ENV_DIR/gateway.env"
DATA_DIR=/var/lib/desk-gateway
# Home outside DATA_DIR so a 0700 data dir cannot block desk-gate (4141208717).
GATE_HOME=/var/lib/desk-gate
GATE_USER=desk-gate
UV=/root/.local/bin/uv
UNIT=desk-gateway.service

install -d -m 0755 -o root -g root /opt

rsync_to_opt() {
  local src=$1
  # rsync --delete is required so removed paths disappear under /opt (4141252905).
  # No tar fallback: non-deleting sync leaves stale gates/rosters deployed.
  if ! command -v rsync >/dev/null 2>&1; then
    echo "install.sh: rsync is required to sync/prune $GATEWAY_ROOT (apt install rsync)" >&2
    exit 1
  fi
  echo "install.sh: syncing $src -> $GATEWAY_ROOT"
  mkdir -p "$GATEWAY_ROOT"
  # Keep the live venv; uv sync refreshes deps after the tree update.
  rsync -a --delete \
    --exclude '.venv/' \
    --exclude '__pycache__/' \
    --exclude '.pytest_cache/' \
    "$src"/ "$GATEWAY_ROOT"/
}

if [[ ! -d "$GATEWAY_ROOT/services/desk-gateway" ]]; then
  if [[ "$SRC_ROOT" != "$GATEWAY_ROOT" && -d "$SRC_ROOT/services/desk-gateway" ]]; then
    rsync_to_opt "$SRC_ROOT"
  elif [[ -d "$OLD_ROOT/services/desk-gateway" ]]; then
    echo "install.sh: migrating $OLD_ROOT -> $GATEWAY_ROOT"
    cp -a "$OLD_ROOT" "$GATEWAY_ROOT"
  else
    echo "install.sh: gateway source missing at $GATEWAY_ROOT (no usable $SRC_ROOT or $OLD_ROOT)" >&2
    exit 1
  fi
elif [[ "$SRC_ROOT" != "$GATEWAY_ROOT" ]]; then
  # Operator pulled/updated a non-canonical tree and reran install — refresh /opt (4141208705).
  if [[ -d "$SRC_ROOT/services/desk-gateway" ]]; then
    rsync_to_opt "$SRC_ROOT"
  else
    echo "install.sh: $GATEWAY_ROOT exists but invoke-from tree $SRC_ROOT looks incomplete" >&2
    exit 1
  fi
else
  echo "install.sh: using in-place checkout at $GATEWAY_ROOT (pull here before rerun)"
fi

[[ -d "$GATEWAY_DIR" ]] || { echo "install.sh: gateway source missing at $GATEWAY_DIR" >&2; exit 1; }
[[ -x "$UV" ]] || { echo "install.sh: uv not found at $UV" >&2; exit 1; }

if ! id -u "$GATE_USER" >/dev/null 2>&1; then
  useradd --system --user-group \
    --home-dir "$GATE_HOME" --create-home \
    --shell /usr/sbin/nologin \
    "$GATE_USER"
  echo "install.sh: created system user $GATE_USER (for future DESK_GATE_USER only — leave unset)"
fi
install -d -m 0750 -o "$GATE_USER" -g "$GATE_USER" "$GATE_HOME"
# Env + gateway data stay root-only; gate home is a sibling path, not under DATA_DIR.
install -d -m 0700 -o root -g root "$ENV_DIR" "$DATA_DIR"

# Traversal for desk-gate without making the whole checkout world-readable (4141208714).
chmod 0755 /opt "$GATEWAY_ROOT"
# Ensure path components under GATEWAY_ROOT are traversable by group/other (dirs only).
find "$GATEWAY_ROOT" -type d -exec chmod 0755 {} +
# Grant desk-gate group read/exec on gates + venv only (after uv sync we re-apply).
chgrp -R "$GATE_USER" "$GATEWAY_ROOT/ci" 2>/dev/null || true
chmod -R g+rX "$GATEWAY_ROOT/ci" 2>/dev/null || true
if [[ -f "$GATEWAY_DIR/.env" ]]; then
  chmod 0600 "$GATEWAY_DIR/.env"
fi

migrate_desk_repo_dir() {
  # Broaden rewrite: unquoted, single/double-quoted, or missing (4141208711).
  local env_file=$1
  python3 - "$env_file" "$GATEWAY_ROOT" <<'PY'
import re, sys
from pathlib import Path
path = Path(sys.argv[1])
target = sys.argv[2]
legacy = "/root/src/repos/programming-desk"
text = path.read_text()
changed = False
pat = re.compile(
    rf'^[ \t]*DESK_REPO_DIR[ \t]*=[ \t]*["\']?{re.escape(legacy)}["\']?[ \t]*$',
    re.MULTILINE,
)
new_text, n = pat.subn(f"DESK_REPO_DIR={target}", text)
if n:
    text = new_text
    changed = True
elif not re.search(r'^[ \t]*DESK_REPO_DIR[ \t]*=', text, re.MULTILINE):
    if text and not text.endswith("\n"):
        text += "\n"
    text += f"DESK_REPO_DIR={target}\n"
    changed = True
if changed:
    path.write_text(text)
    print(f"install.sh: set DESK_REPO_DIR={target} in {path}")
else:
    m = re.search(r'^[ \t]*DESK_REPO_DIR[ \t]*=[ \t]*["\']?([^"\'\n]+)["\']?', text, re.MULTILINE)
    if m and m.group(1).rstrip("/") != target.rstrip("/"):
        print(
            f"install.sh: WARNING: DESK_REPO_DIR={m.group(1)!r} != {target} — "
            "service unit uses /opt; align the env file",
            file=sys.stderr,
        )
PY
}

if [[ -f "$ENV_FILE" ]]; then
  chmod 0600 "$ENV_FILE"
  migrate_desk_repo_dir "$ENV_FILE"
  if grep -qE '^[[:space:]]*DESK_GATE_USER[[:space:]]*=[[:space:]]*[^#[:space:]].*' "$ENV_FILE"; then
    echo "install.sh: WARNING: DESK_GATE_USER is set in $ENV_FILE — leave it empty until drop is verified (4141126594)" >&2
  fi
else
  install -m 0600 -o root -g root "$HERE/gateway.env.example" "$ENV_FILE"
  migrate_desk_repo_dir "$ENV_FILE"
  echo "install.sh: created $ENV_FILE from the template."
  echo "install.sh: fill in the seat passphrases, INTAKE_TOKENS and upstream tokens, then: systemctl restart $UNIT"
  echo "install.sh: leave DESK_GATE_USER empty (do not enable privilege drop yet)"
fi

(cd "$GATEWAY_DIR" && "$UV" sync)

# Re-apply gate-readable perms after uv sync creates/refreshes .venv.
find "$GATEWAY_ROOT" -type d -exec chmod 0755 {} +
chgrp -R "$GATE_USER" "$GATEWAY_ROOT/ci" "$GATEWAY_DIR/.venv"
chmod -R g+rX "$GATEWAY_ROOT/ci" "$GATEWAY_DIR/.venv"
# desk-gate must enter its home
if ! runuser -u "$GATE_USER" -- test -x "$GATE_HOME"; then
  echo "install.sh: $GATE_USER cannot enter $GATE_HOME" >&2
  exit 1
fi
if [[ -f "$GATEWAY_DIR/.env" ]]; then
  chmod 0600 "$GATEWAY_DIR/.env"
fi

PROBE_SCRIPT="$GATEWAY_ROOT/ci/gates/check_ownership.py"
VENV_PY="$GATEWAY_DIR/.venv/bin/python"
[[ -r "$PROBE_SCRIPT" ]] || { echo "install.sh: missing $PROBE_SCRIPT" >&2; exit 1; }
[[ -x "$VENV_PY" ]] || { echo "install.sh: missing executable $VENV_PY" >&2; exit 1; }
if ! runuser -u "$GATE_USER" -- test -r "$PROBE_SCRIPT"; then
  echo "install.sh: $GATE_USER cannot read $PROBE_SCRIPT — fix permissions before DESK_GATE_USER" >&2
  exit 1
fi
# Stronger probe without writing __pycache__ (4141208723 / tip fix 4141252895):
# start the interpreter as desk-gate and compile source in memory only.
if ! runuser -u "$GATE_USER" -- "$VENV_PY" -c 'import sys; assert sys.version_info >= (3, 11)'; then
  echo "install.sh: $GATE_USER cannot run $VENV_PY" >&2
  exit 1
fi
if ! runuser -u "$GATE_USER" -- "$VENV_PY" -c \
  'import pathlib, sys; p = pathlib.Path(sys.argv[1]); compile(p.read_text(encoding="utf-8"), str(p), "exec")' \
  "$PROBE_SCRIPT"; then
  echo "install.sh: $GATE_USER cannot parse $PROBE_SCRIPT" >&2
  exit 1
fi
echo "install.sh: verified $GATE_USER can read/parse ci/gates and run venv python (DESK_GATE_USER still unset)"

install -m 0644 -o root -g root "$HERE/$UNIT" "/etc/systemd/system/$UNIT"
systemctl daemon-reload
systemctl enable --now "$UNIT"
# enable --now leaves an already-running unit on the old code; restart so a rerun after
# git pull actually deploys.
systemctl restart "$UNIT"

sleep 1
echo "+ curl -s http://127.0.0.1:8791/health"
curl -s --max-time 5 http://127.0.0.1:8791/health || echo "install.sh: no answer yet — journalctl -u $UNIT -n 50"
echo
