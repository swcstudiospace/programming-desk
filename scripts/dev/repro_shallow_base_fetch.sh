#!/usr/bin/env bash
# Reproduce the Quality Gates "no merge base" failure.
#
# Sequence, matching the gates job on a moved main:
#   1. Full clone (not shallow).
#   2. Branch off the current main commit.
#   3. Advance main on the remote.
#   4. Fetch that new base tip.
#
# `git fetch --no-tags --depth=1 origin main` records the new tip as a shallow
# boundary, so `origin/main...HEAD` has no merge base. The same clone, fetched
# with an explicit refspec and no --depth, still has the fork commit as the
# merge base.
#
# --old-only stops after the depth-1 fetch and exits 1 when that merge-base
# failure is the one the gates job prints. The default run requires the old
# fetch to fail that way and the unshallowed fetch to succeed.

set -euo pipefail

old_only=0
if [[ "${1:-}" == "--old-only" ]]; then
  old_only=1
elif [[ -n "${1:-}" ]]; then
  echo "usage: $0 [--old-only]" >&2
  exit 2
fi

root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT

remote="$root/remote.git"
origin_work="$root/origin-work"
git init --bare -b main "$remote" >/dev/null
git init -b main "$origin_work" >/dev/null
git -C "$origin_work" config user.email "repro@example.com"
git -C "$origin_work" config user.name "repro"

echo a > "$origin_work/f"
git -C "$origin_work" add f
git -C "$origin_work" commit -m a >/dev/null
git -C "$origin_work" remote add origin "$remote"
git -C "$origin_work" push -q origin main
echo b > "$origin_work/f"
git -C "$origin_work" commit -am b >/dev/null
git -C "$origin_work" push -q origin main
fork=$(git -C "$origin_work" rev-parse HEAD)

prepare_clone() {
  local dest=$1
  git clone -q "$remote" "$dest"
  git -C "$dest" config user.email "repro@example.com"
  git -C "$dest" config user.name "repro"
  git -C "$dest" checkout -q -b feature
  echo c > "$dest/f"
  git -C "$dest" commit -q -am feature
}

prepare_clone "$root/old"
if [[ $old_only -eq 0 ]]; then
  prepare_clone "$root/new"
fi

echo d > "$origin_work/f"
git -C "$origin_work" commit -q -am advance
git -C "$origin_work" push -q origin main

git -C "$root/old" fetch -q --no-tags --depth=1 origin main
set +e
git -C "$root/old" diff --name-only "origin/main...HEAD" >/dev/null 2>"$root/old.err"
old_rc=$?
set -e
if [[ $old_rc -eq 0 ]]; then
  echo "old fetch unexpectedly retained a merge base" >&2
  exit 1
fi
if ! grep -q "no merge base" "$root/old.err"; then
  echo "old fetch failed differently than the gates job (exit $old_rc):" >&2
  cat "$root/old.err" >&2
  exit 2
fi
echo "OLD fetch: origin/main...HEAD has no merge base (diff exit $old_rc)"
cat "$root/old.err"

if [[ $old_only -eq 1 ]]; then
  exit 1
fi

git -C "$root/new" fetch -q --no-tags origin "+refs/heads/main:refs/remotes/origin/main"
base=$(git -C "$root/new" merge-base origin/main HEAD)
if [[ "$base" != "$fork" ]]; then
  echo "new fetch merge-base $base != fork $fork" >&2
  exit 1
fi
git -C "$root/new" diff --name-only "origin/main...HEAD" >/dev/null
if [[ -f "$root/new/.git/shallow" ]]; then
  echo "new fetch left the clone shallow" >&2
  exit 1
fi
echo "NEW fetch: merge-base is the fork $base"
