#!/usr/bin/env bash
# Tests for ci/hooks/g4-preflight.sh.
#
#     bash ci/hooks/g4-preflight.test.sh
#
# The wrapper decides which change document G-4 validates. That decision is not exercised by
# ci/tests/test_gates.py, which calls check_contracts.py directly with an explicit --change —
# so every branch here could break without a gate test noticing. These cover the selection
# order, the one-active-document guard, and the fail-closed path.
#
# Each case runs in a throwaway git repository built from this one's gate, hook and manifest,
# so the real contracts/changes/ is never touched and the order of cases cannot matter.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0

setup() {
    SANDBOX="$(mktemp -d)"
    mkdir -p "$SANDBOX/ci/gates" "$SANDBOX/ci/hooks" "$SANDBOX/contracts/changes/archive"
    cp "$REPO_ROOT/ci/gates/check_contracts.py" "$SANDBOX/ci/gates/"
    cp "$REPO_ROOT/ci/hooks/g4-preflight.sh" "$SANDBOX/ci/hooks/"
    cp "$REPO_ROOT/ownership.yaml" "$SANDBOX/"
    printf 'openapi: 3.1.0\ninfo: {title: t, version: 0.1.0}\npaths: {}\n' > "$SANDBOX/openapi.yaml"
    git -C "$SANDBOX" init -q
    git -C "$SANDBOX" add -A >/dev/null 2>&1
    git -C "$SANDBOX" -c user.email=t@t -c user.name=t commit -qm init >/dev/null 2>&1
}

teardown() { rm -rf "$SANDBOX"; }

# A change document that declares openapi.yaml, so the gate itself passes and the test is
# measuring selection rather than coverage.
doc() {
    cat <<YAML
change_id: $1
proposed_by: bot-06-quality-security
surface: openapi.yaml
breaking: false
version: 1.0.0
summary: $1
semantic_changes: []
YAML
}

# A document declaring a surface this change does NOT touch. Selecting it is detectable:
# the gate rejects it for not covering openapi.yaml.
wrong_doc() {
    cat <<YAML
change_id: $1
proposed_by: bot-06-quality-security
surface: contracts/events/something-else.yaml
breaking: false
version: 1.0.0
summary: $1
semantic_changes: []
YAML
}

run() { ( cd "$SANDBOX" && bash ci/hooks/g4-preflight.sh "$@" 2>&1 ); }

check() {
    local name="$1" expected_rc="$2" actual_rc="$3" output="$4" must_contain="${5:-}"
    if [[ "$actual_rc" != "$expected_rc" ]]; then
        echo "  FAIL  $name — expected exit $expected_rc, got $actual_rc"
        echo "$output" | sed 's/^/          /' | tail -4
        FAIL=$((FAIL + 1)); return
    fi
    if [[ -n "$must_contain" && "$output" != *"$must_contain"* ]]; then
        echo "  FAIL  $name — output did not contain: $must_contain"
        echo "$output" | sed 's/^/          /' | tail -4
        FAIL=$((FAIL + 1)); return
    fi
    echo "  ok    $name"
    PASS=$((PASS + 1))
}

echo "g4-preflight.sh"

# 1. Nothing to gate.
setup
out=$(run README.md); rc=$?
check "no document, no contract surface touched -> passes" 0 "$rc" "$out" "no contract surfaces touched"
teardown

# 2. Fail closed. This is the property that must never regress.
setup
out=$(run openapi.yaml); rc=$?
check "no document, contract surface touched -> fails closed" 1 "$rc" "$out" "no change document"
teardown

# 3. The document this change proposes.
setup
doc feat-a > "$SANDBOX/contracts/changes/feat-a.yaml"
out=$(run openapi.yaml contracts/changes/feat-a.yaml); rc=$?
check "active document in the change -> selected" 0 "$rc" "$out" "contracts/changes/feat-a.yaml"
teardown

# 4. Present in the tree but not in the file list — the fallback.
setup
doc feat-a > "$SANDBOX/contracts/changes/feat-a.yaml"
out=$(run openapi.yaml); rc=$?
check "single active document, not in the change -> falls back to it" 0 "$rc" "$out" "contracts/changes/feat-a.yaml"
teardown

# 5. Archive-only move. Regression test: the first version of this wrapper looked only at
#    the active directory, so archiving — which empties it while still touching contracts/**
#    — fell through to the fail-closed path and made the protocol's archive step impossible.
setup
doc feat-old > "$SANDBOX/contracts/changes/archive/feat-old.yaml"
out=$(run contracts/changes/archive/feat-old.yaml); rc=$?
check "archive-only change -> archived document selected" 0 "$rc" "$out" "archive/feat-old.yaml"
teardown

# 6. Archive the old one and propose a new one in the same change: the normal flow.
#    The ACTIVE document must win. The archived one declares a surface this change does not
#    touch, so selecting it would fail the gate and this test.
setup
wrong_doc feat-old > "$SANDBOX/contracts/changes/archive/feat-old.yaml"
doc feat-new > "$SANDBOX/contracts/changes/feat-new.yaml"
out=$(run contracts/changes/archive/feat-old.yaml contracts/changes/feat-new.yaml openapi.yaml); rc=$?
check "archive plus new document -> the new one wins" 0 "$rc" "$out" "contracts/changes/feat-new.yaml"
teardown

# 7/8. The guard, both ways round. It is a statement about the repository, so supplying a
#      document in the change must not buy a pass past it.
setup
doc feat-a > "$SANDBOX/contracts/changes/feat-a.yaml"
doc feat-b > "$SANDBOX/contracts/changes/feat-b.yaml"
out=$(run openapi.yaml); rc=$?
check "two active documents -> refused" 1 "$rc" "$out" "more than one active change document"
out=$(run openapi.yaml contracts/changes/feat-b.yaml); rc=$?
check "two active documents, one supplied -> still refused" 1 "$rc" "$out" "more than one active change document"
teardown

echo
echo "$PASS passed, $FAIL failed"
[[ "$FAIL" -eq 0 ]]
