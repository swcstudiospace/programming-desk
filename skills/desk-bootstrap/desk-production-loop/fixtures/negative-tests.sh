#!/usr/bin/env bash
# Negative tests for verify.sh: prove the check FAILS when a rule is removed.
#
# Asserting a rule is present is easy. Asserting its absence is caught is the part that makes the
# check worth anything, and it needs the rule removed and the check re-run. Doing that in the working
# tree is what this script exists to avoid: the restore step is the hazard, not the mutation.
# `git checkout -- SKILL.md` restores from the index, so it discards every other uncommitted change
# in that file -- which on a round of review fixes is the whole round's work. Earlier rounds of this
# receipt did exactly that and got away with it.
#
# So each case copies the tracked tree to a scratch directory with `git archive`, overlays the
# WORKING-tree copies of the files under test (so uncommitted edits are what gets tested, which is
# the point when the edits are the fix under review), mutates the copy, and runs verify.sh against it
# through DESK_LOOP_ROOT. The working tree is never written to. The scratch directory is removed on
# exit, including on failure, via trap.
#
# Each mutation asserts its own anchor was found. A mutation whose anchor has drifted would otherwise
# no-op, the check would pass, and the negative test would report success while testing nothing --
# a negative test that cannot fail is worse than none, because it is cited as evidence.
#
#   bash skills/desk-bootstrap/desk-production-loop/fixtures/negative-tests.sh
#
# Exits 0 when every case failed as intended, 1 otherwise. Cited by
# .receipts/bot-00-programming-lead/lead-production-loop-spe-4794.json.
set -uo pipefail
cd "$(dirname "$0")/../../../.."
REPO=$(pwd)
VERIFY=skills/desk-bootstrap/desk-production-loop/verify.sh
LOOP_DIR=skills/desk-bootstrap/desk-production-loop
rc=0

scratch=""
cleanup() { [ -n "$scratch" ] && rm -rf "$scratch"; }
trap cleanup EXIT

new_scratch() {
  cleanup
  scratch=$(mktemp -d "${TMPDIR:-/tmp}/desk-loop-negtest.XXXXXX")
  git archive --format=tar HEAD | tar -x -C "$scratch"
  # overlay the working-tree versions of the files under test
  mkdir -p "$scratch/$LOOP_DIR/fixtures" "$scratch/docs"
  cp "$REPO/$LOOP_DIR/SKILL.md" "$REPO/$VERIFY" "$scratch/$LOOP_DIR/"
  cp "$REPO/$LOOP_DIR/fixtures/"* "$scratch/$LOOP_DIR/fixtures/"
  cp "$REPO/docs/desk-operating-model.md" "$scratch/docs/"
  cp "$REPO/skills/desk-bootstrap/SKILL.md" "$scratch/skills/desk-bootstrap/"
}

# run verify.sh against the scratch tree; echo its exit code
check() { DESK_LOOP_ROOT="$scratch" bash "$REPO/$VERIFY" >/dev/null 2>&1; echo $?; }
check_msg() { DESK_LOOP_ROOT="$scratch" bash "$REPO/$VERIFY" 2>&1 | tail -1; }

# replace a literal in a scratch file, failing loudly if the anchor is gone
mutate() { # <relative path> <find> <replace>
  python3 - "$scratch/$1" "$2" "$3" <<'PY'
import sys
from pathlib import Path
p, find, repl = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
s = p.read_text()
n = s.replace(find, repl, 1)
assert n != s, f"anchor not found in {p}: {find[:60]!r}"
p.write_text(n)
PY
}

case_expect_fail() { # <name> <expected FAIL substring>
  local name=$1 want=$2 got msg
  got=$(check); msg=$(check_msg)
  if [ "$got" = "1" ] && [[ "$msg" == *"$want"* ]]; then
    echo "  PASS  $name -> exit 1, $msg"
  else
    echo "  FAIL  $name -> exit $got, $msg  (expected exit 1 containing '$want')"
    rc=1
  fi
}

echo "negative tests for $VERIFY"

echo "[0] baseline: an unmutated scratch tree must PASS"
new_scratch
got=$(check)
if [ "$got" = "0" ]; then echo "  PASS  baseline -> exit 0"
else echo "  FAIL  baseline -> exit $got (the scratch overlay is wrong, not the rules)"; rc=1; fi

echo "[1] R6d: reinstate the superseded typed-routing claim"
new_scratch
mutate "$LOOP_DIR/SKILL.md" \
  '**This is a documented contract gap, not a design.**' \
  'The catalogue routes on kind, so swapping it misroutes the turn.' || { echo "  FAIL  mutation"; rc=1; }
case_expect_fail "R6d gap named" "R6d gap named"

echo "[2] R7a: put the degraded turn ack back in approvals[]"
new_scratch
mutate "$LOOP_DIR/SKILL.md" \
  'in the receipt under **`loop_acks`** — **not `approvals`**, see below —' \
  'in the receipt under `approvals`' || { echo "  FAIL  mutation"; rc=1; }
case_expect_fail "R7a stale approvals instruction removed" "R7a stale approvals instruction removed"

echo "[3] R8a: reinstate the tip-advancing stamp as the documented path"
new_scratch
mutate "$LOOP_DIR/SKILL.md" \
  '> **An approval must be bound to a sha, and must not create one.**' \
  '> The first stamp is a reviewed human act, not a tool call.' || { echo "  FAIL  mutation"; rc=1; }
case_expect_fail "R8a binding rule / stale workaround" "R8a"

echo "[4] P2-8: remove a seat template"
new_scratch
rm -f "$scratch/grokbot/templates/IOS.md"
case_expect_fail "missing seat template" "missing seat template"

echo "[5] R8b: make the four-field G-6 fixture stop reproducing the false PASS"
new_scratch
python3 - "$scratch/$LOOP_DIR/fixtures/g6-turn-ack-four-fields.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1]); d = json.loads(p.read_text())
d["approvals"][0].pop("blast_radius")      # now G-6 fails, so the documented exit 0 is wrong
p.write_text(json.dumps(d, indent=2))
PY
case_expect_fail "R8b fixture exit-code drift" "R8b g6-turn-ack-four-fields.json"

echo
if [ "$rc" = "0" ]; then echo "ok: every case failed as intended, and the working tree was never written to"
else echo "NOT OK: a negative test did not fail as intended -- verify.sh is weaker than it claims"; fi
exit $rc
