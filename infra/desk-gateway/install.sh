#!/usr/bin/env bash
# Install or update the desk-gateway systemd service on the VPS. Safe to rerun.
# Does not touch nginx, DNS or certificates — that is install-nginx.sh.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "install.sh: must run as root" >&2; exit 1; }

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY_DIR=/root/src/repos/programming-desk/services/desk-gateway
ENV_DIR=/etc/desk-gateway
ENV_FILE="$ENV_DIR/gateway.env"
DATA_DIR=/var/lib/desk-gateway
UV=/root/.local/bin/uv
UNIT=desk-gateway.service

[[ -d "$GATEWAY_DIR" ]] || { echo "install.sh: gateway source missing at $GATEWAY_DIR" >&2; exit 1; }
[[ -x "$UV" ]] || { echo "install.sh: uv not found at $UV" >&2; exit 1; }

install -d -m 0700 -o root -g root "$ENV_DIR" "$DATA_DIR"

if [[ -f "$ENV_FILE" ]]; then
  chmod 0600 "$ENV_FILE"
else
  install -m 0600 -o root -g root "$HERE/gateway.env.example" "$ENV_FILE"
  echo "install.sh: created $ENV_FILE from the template."
  echo "install.sh: fill in the seat passphrases, INTAKE_TOKENS and upstream tokens, then: systemctl restart $UNIT"
fi

(cd "$GATEWAY_DIR" && "$UV" sync)

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
