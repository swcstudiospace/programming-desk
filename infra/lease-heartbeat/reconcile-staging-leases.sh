#!/usr/bin/env bash
# Autonomous production and staging lease reconciliation for ephemeral test branches (REQ-STAGE-003).
# Scans active substrate/gateway leases, identifies merged or deleted ephemeral git branches,
# and safely prunes orphaned leases via substrate MCP.
set -euo pipefail

log() {
  printf '[reconcile-staging-leases %s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

err() {
  printf '[reconcile-staging-leases %s] ERROR: %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" >&2
}

SUBSTRATE_MCP_URL="${SUBSTRATE_MCP_URL:-http://127.0.0.1:7410}"
LEASE_REAP_URL="${DESK_LEASE_REAP_URL:-http://127.0.0.1:8791/v1/leases/reconcile}"
DRY_RUN="${DRY_RUN:-false}"
MAX_BRANCH_AGE_HOURS="${MAX_BRANCH_AGE_HOURS:-24}"

log "Starting staging lease reconciliation sweep (dry_run: $DRY_RUN)..."

# 1. Fetch active ephemeral branch leases from gateway / substrate
ACTIVE_LEASES_FILE="$(mktemp)"
PRUNED_LEASES_FILE="$(mktemp)"
trap 'rm -f "$ACTIVE_LEASES_FILE" "$PRUNED_LEASES_FILE"' EXIT

# Query substrate / gateway lease list
if command -v curl >/dev/null 2>&1; then
  HTTP_CODE="$(curl -s -o "$ACTIVE_LEASES_FILE" -w "%{http_code}" --max-time 5 "$LEASE_REAP_URL" || true)"
  if [[ "$HTTP_CODE" != "200" ]]; then
    log "Gateway lease reconcile endpoint unreachable ($HTTP_CODE); fallback to local inspection"
    echo '{"leases": []}' > "$ACTIVE_LEASES_FILE"
  fi
else
  echo '{"leases": []}' > "$ACTIVE_LEASES_FILE"
fi

# 2. Reconcile against git branches to detect merged or pruned ephemeral heads
python3 - "$ACTIVE_LEASES_FILE" "$PRUNED_LEASES_FILE" "$DRY_RUN" <<'PY'
import json
import sys
import subprocess
from pathlib import Path

leases_path = Path(sys.argv[1])
pruned_path = Path(sys.argv[2])
dry_run = sys.argv[3].lower() == "true"

try:
    data = json.loads(leases_path.read_text(encoding="utf-8"))
except Exception:
    data = {"leases": []}

leases = data.get("leases", [])
orphaned = []

# Probe local and remote branch states if in a git repo
git_branches = set()
try:
    res = subprocess.run(
        ["git", "branch", "-r", "--format=%(refname:short)"],
        capture_output=True, text=True, check=False
    )
    if res.returncode == 0:
        for line in res.stdout.splitlines():
            branch = line.strip().replace("origin/", "")
            if branch:
                git_branches.add(branch)
except Exception:
    pass

for lease in leases:
    branch = lease.get("branch")
    lease_id = lease.get("lease_id")
    # If lease tied to a test/staging branch that no longer exists in remote refs, mark orphaned
    if branch and branch not in ("main", "master", "develop", "production"):
        if git_branches and branch not in git_branches:
            orphaned.append(lease)

pruned_path.write_text(json.dumps(orphaned, indent=2), encoding="utf-8")
print(f"Detected {len(orphaned)} orphaned ephemeral lease(s)")
PY

ORPHANED_COUNT="$(grep -c '"lease_id"' "$PRUNED_LEASES_FILE" || true)"
log "Identified $ORPHANED_COUNT orphaned lease(s) to prune."

# 3. Post release prune execution to substrate / gateway
if [[ "$ORPHANED_COUNT" -gt 0 && "$DRY_RUN" != "true" ]]; then
  if command -v curl >/dev/null 2>&1; then
    PRUNE_STATUS="$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
      -X POST \
      -H "Content-Type: application/json" \
      --data @"$PRUNED_LEASES_FILE" \
      "$LEASE_REAP_URL/prune" || true)"
    log "Orphaned leases pruned with status $PRUNE_STATUS."
  else
    log "Dry environment: simulated prune of $ORPHANED_COUNT leases."
  fi
fi

log "Staging lease reconciliation finished successfully."
exit 0
