#!/usr/bin/env bash
# Idempotent file installer for the seat-lease heartbeat and the lease reap timer.
#
# Default: write or check files. Does not daemon-reload, enable, or start anything.
# --enable: systemctl enable the two timers. It does not start them.
#
# Never prints environment values. Messages name variables and shipped literals only.
#
#   install.sh [--sysroot DIR] [--enable]
#
# --sysroot prefixes /etc and /var (tests and scratch trees). The default is /.
# A sysroot of / requires root. --enable is refused for any other sysroot.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXAMPLE="$HERE/heartbeat.env.example"
SYSROOT=/
ENABLE=0

usage() {
  echo "usage: install.sh [--sysroot DIR] [--enable]"
  echo "default: write or check unit files and heartbeat.env; do not enable timers"
  echo "--enable: systemctl enable the heartbeat and reap timers (does not start them)"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable)
      ENABLE=1
      shift
      ;;
    --sysroot)
      if [[ $# -lt 2 ]]; then
        echo "install.sh: --sysroot needs a directory" >&2
        exit 2
      fi
      SYSROOT=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "install.sh: unknown argument" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$SYSROOT" != "/" ]]; then
  if [[ "$SYSROOT" != /* ]]; then
    echo "install.sh: --sysroot must be an absolute path" >&2
    exit 2
  fi
  mkdir -p "$SYSROOT"
  SYSROOT="$(cd "$SYSROOT" && pwd -P)"
fi

if [[ "$SYSROOT" == "/" && "$(id -u)" -ne 0 ]]; then
  echo "install.sh: must run as root when --sysroot is /" >&2
  exit 1
fi

if [[ "$ENABLE" -eq 1 && "$SYSROOT" != "/" ]]; then
  echo "install.sh: --enable is refused when --sysroot is not /" >&2
  exit 1
fi

require_line() {
  local file=$1 line=$2
  if ! grep -q -x -F -- "$line" "$file"; then
    echo "install.sh: $(basename "$file") is missing shipped line: $line" >&2
    exit 1
  fi
}

require_line "$HERE/desk-lease-heartbeat.service" "Type=oneshot"
require_line "$HERE/desk-lease-heartbeat.service" "WorkingDirectory=/opt/desk-gateway/programming-desk"
require_line "$HERE/desk-lease-heartbeat.service" "ExecStart=/opt/desk-gateway/programming-desk/services/desk-lease-heartbeat/.venv/bin/desk-lease-heartbeat renew"
require_line "$HERE/desk-lease-heartbeat.service" "TimeoutStartSec=10"
require_line "$HERE/desk-lease-heartbeat.timer" "OnUnitActiveSec=60"
require_line "$HERE/desk-lease-heartbeat.timer" "RandomizedDelaySec=5"
require_line "$HERE/substrate-lease-reap.service" "Type=oneshot"
require_line "$HERE/substrate-lease-reap.service" "WorkingDirectory=/opt/desk-gateway/programming-desk"
require_line "$HERE/substrate-lease-reap.service" "ExecStart=/opt/desk-gateway/programming-desk/infra/lease-heartbeat/substrate-lease-reap.sh"
require_line "$HERE/substrate-lease-reap.timer" "OnUnitActiveSec=45"
require_line "$HERE/substrate-lease-reap.timer" "RandomizedDelaySec=5"

# Shipped unit literals. Empty env values use these, plus TTL 900.
LITERAL_INTERVAL=60
LITERAL_JITTER=5
LITERAL_TIMEOUT=10
DEFAULT_TTL=900

REQUIRED=(
  LEASE_SEAT
  LEASE_HOLDER_ID
  LEASE_ENDPOINT_URL
  LEASE_ENDPOINT_TOKEN
  LEASE_TTL_S
  LEASE_INTERVAL_S
  LEASE_JITTER_S
  LEASE_TIMEOUT_S
  LEASE_MAX_MISSED
  LEASE_STATE_DIR
  LEASE_HELD_FILE
  LEASE_LOG_LEVEL
  LEASE_LOG_BYTES
)

declare -A ENV_PRESENT=()
declare -A ENV_VALUE=()

load_env() {
  local file=$1 line key value
  ENV_PRESENT=()
  ENV_VALUE=()
  while IFS= read -r line || [[ -n "$line" ]]; do
    line=${line%$'\r'}
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$line" =~ ^[[:space:]]*[#\;] ]] && continue
    if [[ "$line" != *"="* ]]; then
      echo "install.sh: env file has a line that is not KEY=VALUE" >&2
      exit 1
    fi
    key=${line%%=*}
    value=${line#*=}
    key=${key#"${key%%[![:space:]]*}"}
    key=${key%"${key##*[![:space:]]}"}
    value=${value#"${value%%[![:space:]]*}"}
    value=${value%"${value##*[![:space:]]}"}
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value=${value:1:${#value}-2}
    fi
    if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      echo "install.sh: env file has a key that is not a bare name" >&2
      exit 1
    fi
    ENV_PRESENT["$key"]=1
    ENV_VALUE["$key"]=$value
  done < "$file"
}

read_cadence() {
  local name=$1 default=$2 raw
  raw=${ENV_VALUE[$name]-}
  if [[ -z "$raw" ]]; then
    printf '%s' "$default"
    return 0
  fi
  if [[ ! "$raw" =~ ^[0-9]+$ || "$raw" =~ ^0[0-9] || ${#raw} -gt 9 ]]; then
    echo "install.sh: $name is not a canonical non-negative integer" >&2
    return 1
  fi
  printf '%s' "$raw"
}

check_literal() {
  local name=$1 expected=$2 raw
  raw=${ENV_VALUE[$name]-}
  if [[ -z "$raw" ]]; then
    return 0
  fi
  if [[ "$raw" != "$expected" ]]; then
    echo "install.sh: $name does not match the shipped unit literal ($expected)" >&2
    return 1
  fi
}

ENV_DIR="$SYSROOT/etc/desk-lease-heartbeat"
ENV_FILE="$ENV_DIR/heartbeat.env"
STATE_DIR="$SYSROOT/var/lib/desk-lease-heartbeat"
UNIT_DIR="$SYSROOT/etc/systemd/system"

install -d -m 0700 "$ENV_DIR"
if [[ -L "$ENV_FILE" ]]; then
  echo "install.sh: refusing to follow a symlink at $ENV_FILE" >&2
  exit 1
fi
if [[ ! -e "$ENV_FILE" ]]; then
  (umask 077; cp --update=none "$EXAMPLE" "$ENV_FILE")
  echo "install.sh: created $ENV_FILE mode 0600"
else
  echo "install.sh: $ENV_FILE already present; contents unchanged"
fi
chmod 0600 "$ENV_FILE"
if [[ "$(id -u)" -eq 0 ]]; then
  chown root:root "$ENV_DIR" "$ENV_FILE"
fi

load_env "$ENV_FILE"

missing=0
for name in "${REQUIRED[@]}"; do
  if [[ -z "${ENV_PRESENT[$name]-}" ]]; then
    echo "install.sh: missing required variable $name" >&2
    missing=1
  fi
done
if [[ "$missing" -ne 0 ]]; then
  exit 1
fi

if ! interval="$(read_cadence LEASE_INTERVAL_S "$LITERAL_INTERVAL")"; then
  exit 1
fi
if ! jitter="$(read_cadence LEASE_JITTER_S "$LITERAL_JITTER")"; then
  exit 1
fi
if ! timeout="$(read_cadence LEASE_TIMEOUT_S "$LITERAL_TIMEOUT")"; then
  exit 1
fi
if ! ttl="$(read_cadence LEASE_TTL_S "$DEFAULT_TTL")"; then
  exit 1
fi

if (( 10#$timeout >= 10#$interval )); then
  echo "install.sh: timing invariant failed: LEASE_TIMEOUT_S must be < LEASE_INTERVAL_S" >&2
  exit 1
fi
if (( (10#$interval + 10#$jitter + 10#$timeout) * 3 > 10#$ttl )); then
  echo "install.sh: timing invariant failed: LEASE_INTERVAL_S + LEASE_JITTER_S + LEASE_TIMEOUT_S must be <= LEASE_TTL_S / 3" >&2
  exit 1
fi

check_literal LEASE_INTERVAL_S "$LITERAL_INTERVAL"
check_literal LEASE_JITTER_S "$LITERAL_JITTER"
check_literal LEASE_TIMEOUT_S "$LITERAL_TIMEOUT"

install -d -m 0755 "$UNIT_DIR"
install -m 0644 "$HERE/desk-lease-heartbeat.service" "$UNIT_DIR/desk-lease-heartbeat.service"
install -m 0644 "$HERE/desk-lease-heartbeat.timer" "$UNIT_DIR/desk-lease-heartbeat.timer"
install -m 0644 "$HERE/substrate-lease-reap.service" "$UNIT_DIR/substrate-lease-reap.service"
install -m 0644 "$HERE/substrate-lease-reap.timer" "$UNIT_DIR/substrate-lease-reap.timer"
install -d -m 0700 "$STATE_DIR"
if [[ "$(id -u)" -eq 0 ]]; then
  chown root:root "$STATE_DIR"
fi

echo "install.sh: unit files written under $UNIT_DIR"
echo "install.sh: timers not enabled"

if [[ "$ENABLE" -eq 1 ]]; then
  systemctl daemon-reload
  systemctl enable desk-lease-heartbeat.timer substrate-lease-reap.timer
  echo "install.sh: enabled desk-lease-heartbeat.timer and substrate-lease-reap.timer"
  echo "install.sh: timers were not started"
fi
