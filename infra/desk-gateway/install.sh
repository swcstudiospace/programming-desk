#!/usr/bin/env bash
# Install or update the desk-gateway systemd service on the VPS. Safe to rerun.
# Does not touch nginx, DNS or certificates — that is install-nginx.sh.
#
# Layout (Greptile P1 4141126594): the desk checkout lives under /opt/programming-desk
# so a future DESK_GATE_USER can traverse the tree and run ci/gates scripts. Do NOT
# set DESK_GATE_USER in the live env until that drop is verified separately.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "install.sh: must run as root" >&2; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY_ROOT=/opt/programming-desk
OLD_ROOT=/root/src/repos/programming-desk
GATEWAY_DIR="$GATEWAY_ROOT/services/desk-gateway"
ENV_DIR=/etc/desk-gateway
ENV_FILE="$ENV_DIR/gateway.env"
DATA_DIR=/var/lib/desk-gateway
GATE_HOME="$DATA_DIR/gate-home"
GATE_USER=desk-gate
UV=/root/.local/bin/uv
UNIT=desk-gateway.service

install -d -m 0755 -o root -g root /opt

if [[ ! -d "$GATEWAY_ROOT" ]]; then
  if [[ -d "$OLD_ROOT" ]]; then
    echo "install.sh: migrating $OLD_ROOT -> $GATEWAY_ROOT"
    cp -a "$OLD_ROOT" "$GATEWAY_ROOT"
  else
    echo "install.sh: gateway source missing at $GATEWAY_ROOT (and no legacy $OLD_ROOT)" >&2
    exit 1
  fi
fi

[[ -d "$GATEWAY_DIR" ]] || { echo "install.sh: gateway source missing at $GATEWAY_DIR" >&2; exit 1; }
[[ -x "$UV" ]] || { echo "install.sh: uv not found at $UV" >&2; exit 1; }

# World-traversable path components so a future gate account can read ci/gates and
# execute the gateway venv python. Secrets stay in /etc/desk-gateway (0600).
chmod 0755 /opt "$GATEWAY_ROOT"
# Prefer a+rX over recursive 0777: dirs get +x for traversal, files get +r only.
chmod -R a+rX "$GATEWAY_ROOT"
# Re-lock anything that must not be world-readable if present under the tree.
if [[ -f "$GATEWAY_ROOT/services/desk-gateway/.env" ]]; then
  chmod 0600 "$GATEWAY_ROOT/services/desk-gateway/.env"
fi

if ! id -u "$GATE_USER" >/dev/null 2>&1; then
  useradd --system --user-group \
    --home-dir "$GATE_HOME" --create-home \
    --shell /usr/sbin/nologin \
    "$GATE_USER"
  echo "install.sh: created system user $GATE_USER (for future DESK_GATE_USER only — leave unset)"
fi
install -d -m 0750 -o "$GATE_USER" -g "$GATE_USER" "$GATE_HOME"

install -d -m 0700 -o root -g root "$ENV_DIR" "$DATA_DIR"

if [[ -f "$ENV_FILE" ]]; then
  chmod 0600 "$ENV_FILE"
  # Migrate a stock old default path; never invent DESK_GATE_USER.
  if grep -qE '^DESK_REPO_DIR=/root/src/repos/programming-desk[[:space:]]*$' "$ENV_FILE"; then
    sed -i 's|^DESK_REPO_DIR=/root/src/repos/programming-desk[[:space:]]*$|DESK_REPO_DIR=/opt/programming-desk|' "$ENV_FILE"
    echo "install.sh: updated DESK_REPO_DIR in $ENV_FILE to $GATEWAY_ROOT"
  fi
  if grep -qE '^DESK_GATE_USER=.+' "$ENV_FILE"; then
    echo "install.sh: WARNING: DESK_GATE_USER is set in $ENV_FILE — leave it empty until drop is verified (4141126594)" >&2
  fi
else
  install -m 0600 -o root -g root "$HERE/gateway.env.example" "$ENV_FILE"
  echo "install.sh: created $ENV_FILE from the template."
  echo "install.sh: fill in the seat passphrases, INTAKE_TOKENS and upstream tokens, then: systemctl restart $UNIT"
  echo "install.sh: leave DESK_GATE_USER empty (do not enable privilege drop yet)"
fi

(cd "$GATEWAY_DIR" && "$UV" sync)
# uv sync may tighten modes; restore traversal for the gate account probe.
chmod -R a+rX "$GATEWAY_ROOT"
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
if ! runuser -u "$GATE_USER" -- test -x "$VENV_PY"; then
  echo "install.sh: $GATE_USER cannot execute $VENV_PY — fix permissions before DESK_GATE_USER" >&2
  exit 1
fi
echo "install.sh: verified $GATE_USER can read ci/gates and execute venv python (DESK_GATE_USER still unset)"

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
