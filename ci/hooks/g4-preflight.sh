#!/usr/bin/env bash
# G-4 pre-flight — resolve the active contract change document and run the gate with it.
#
# Used by the g4-contract-preflight hook in .pre-commit-config.yaml, and runnable by hand:
#
#     bash ci/hooks/g4-preflight.sh contracts/api/notifications.yaml
#     bash ci/hooks/g4-preflight.sh $(git diff --cached --name-only)
#
# Why this exists rather than calling check_contracts.py straight from the hook: the gate
# needs --change, and a hook only receives file names. Without the document the gate reports
# "no change document supplied" on every run, including runs where the contributor has
# written a perfectly good one — so the pre-flight could never tell anyone they were ready.
#
# Resolving the document here also puts the one-active-document rule somewhere executable.
# contracts/changes/ is globbed by whoever invokes the gate, so a second document left in it
# makes the selection ambiguous; this fails instead of picking one.
#
# PYTHON lets a caller point at a specific interpreter (pre-commit's hook venv, which has
# pyyaml). Defaults to python3 for a human running it directly.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-python3}"
GATE="ci/gates/check_contracts.py"

# Selection, in the same order the live workflow uses.
#
# 1. A change document among the files handed to this run. This is the definitive signal:
#    it is the document THIS change adds, which is what .github/workflows/gates.yml selects
#    with `git diff --name-only --diff-filter=d ... -- contracts/changes`. It also covers the
#    archive case — moving a merged document to contracts/changes/archive/ still touches a
#    contract surface, so the gate wants a document, and the archived copy is the right one.
# 2. Otherwise the single active document in contracts/changes/.
#
# Keeping this in step with the workflow matters more than the few lines it costs: two
# different rules for choosing a change document is the same class of bug as two workflows
# drifting apart.
FROM_DIFF=""
for f in "$@"; do
    case "$f" in
        contracts/changes/*.yaml|contracts/changes/*.yml) FROM_DIFF="$f"; break ;;
        contracts/changes/*/*.yaml|contracts/changes/*/*.yml) FROM_DIFF="$f"; break ;;
    esac
done

if [[ -n "$FROM_DIFF" ]]; then
    echo "G-4 pre-flight — using change document from this change: $FROM_DIFF"
    exec "$PYTHON" "$GATE" --files "$@" --change "$FROM_DIFF"
fi

shopt -s nullglob
DOCS=(contracts/changes/*.yaml)
shopt -u nullglob

if (( ${#DOCS[@]} > 1 )); then
    cat >&2 <<MSG
G-4 pre-flight — more than one active change document in contracts/changes/:

$(printf '    %s\n' "${DOCS[@]}")

Whoever invokes the gate picks one by globbing this directory, so two documents means the
gate may validate a change that neither describes. Exactly one document is active at a time:
the one this change is proposing.

Move the documents whose changes have already merged to contracts/changes/archive/ — the
glob is not recursive, so they stay readable as history without being selected.
MSG
    exit 1
fi

if (( ${#DOCS[@]} == 0 )); then
    # No document. The gate still fails if a contract surface is touched, which is the point.
    exec "$PYTHON" "$GATE" --files "$@"
fi

echo "G-4 pre-flight — using the active change document: ${DOCS[0]}"
exec "$PYTHON" "$GATE" --files "$@" --change "${DOCS[0]}"
