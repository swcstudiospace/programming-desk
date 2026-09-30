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

# The one-active-document guard runs FIRST, and unconditionally.
#
# It is a statement about the repository, not about how this run picked its document: two
# active documents means the next caller to glob this directory may validate a change
# neither describes. Running it only on the fallback path would let a change that supplies
# its own document sail past an ambiguity it is leaving behind for everyone else.
shopt -s nullglob
ACTIVE=(contracts/changes/*.yaml contracts/changes/*.yml)
shopt -u nullglob

if (( ${#ACTIVE[@]} > 1 )); then
    cat >&2 <<MSG
G-4 pre-flight — more than one active change document in contracts/changes/:

$(printf '    %s\n' "${ACTIVE[@]}")

Whoever invokes the gate picks one by globbing this directory, so two documents means the
gate may validate a change that neither describes. Exactly one document is active at a time:
the one this change is proposing.

Move the documents whose changes have already merged to contracts/changes/archive/ — the
glob is not recursive, so they stay readable as history without being selected.
MSG
    exit 1
fi

# Selection, in the same order the live workflow uses, with archived history ranked last.
#
# 1. An ACTIVE change document among the files handed to this run — the document this change
#    is proposing. This is what .github/workflows/gates.yml selects with
#    `git diff --name-only --diff-filter=d ... -- contracts/changes`.
# 2. An ARCHIVED one among them. Moving a merged document to contracts/changes/archive/
#    still touches contracts/**, so the gate wants a document and the archived copy is the
#    only one the change has.
# 3. Otherwise the single active document already in the tree.
#
# The order between 1 and 2 matters: a change that archives the previous document AND
# proposes a new one contains both, and validating the archived record against the new
# change would reject a perfectly good pull request.
#
# Note these are `case` patterns, not pathname globs — `*` matches `/` here, so
# contracts/changes/*.yaml would also match contracts/changes/archive/x.yaml. The archive
# pattern has to be tested first or it can never match.
FROM_CHANGE_ACTIVE=""
FROM_CHANGE_ARCHIVED=""
for f in "$@"; do
    case "$f" in
        contracts/changes/archive/*.yaml|contracts/changes/archive/*.yml)
            [[ -z "$FROM_CHANGE_ARCHIVED" ]] && FROM_CHANGE_ARCHIVED="$f" ;;
        contracts/changes/*.yaml|contracts/changes/*.yml)
            [[ -z "$FROM_CHANGE_ACTIVE" ]] && FROM_CHANGE_ACTIVE="$f" ;;
    esac
done

CHANGE="${FROM_CHANGE_ACTIVE:-${FROM_CHANGE_ARCHIVED:-${ACTIVE[0]:-}}}"

if [[ -n "$CHANGE" ]]; then
    echo "G-4 pre-flight — using change document: $CHANGE"
    exec "$PYTHON" "$GATE" --files "$@" --change "$CHANGE"
fi

# No document anywhere. The gate still fails if a contract surface is touched, which is
# the point — this is the fail-closed path, not a skip.
exec "$PYTHON" "$GATE" --files "$@"
