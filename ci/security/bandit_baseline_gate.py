#!/usr/bin/env python3
"""Bandit baseline gate for the security PR gate (SPE-5162, security-pr.yml).

Bandit is scoped to this PR's changed .py files (see security-pr.yml's Bandit step
comment), not `bandit -r .`, because a whole-repo scan trips a real, pre-existing HIGH
finding (B324, SHA1 in a WebSocket handshake) in infra/unified-lsp-broker/broker.py — a
file owned by a different bot. Scoping to changed files avoids that UNLESS a PR touches
broker.py itself for an unrelated reason (e.g. adding a function elsewhere in the file):
then the whole file is back in scope and the same pre-existing finding blocks an edit
that never touched the flagged line.

This script closes that gap without touching broker.py (which QUALITY does not own,
per ownership.yaml's infra/** -> bot-05-infrastructure rule, so a `# nosec` fix there is
not this bot's to make): it runs Bandit against each changed file both at HEAD and at
the base ref, and only fails on findings that are NEW at HEAD. A finding is identified
by (file, test_id, normalized flagged-line text) rather than (file, test_id, line
number), so it survives line-number drift caused by unrelated edits elsewhere in the
file — only the actual flagged line's content, not its position, has to be unchanged
for a finding to count as pre-existing.

Usage:
    python3 ci/security/bandit_baseline_gate.py --base-ref origin/main --ini ci/security/bandit.ini -- <files...>
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

LINE_RE = re.compile(r"^\s*(\d+)\s(.*)$")


def run_bandit_json(paths: list[str], ini: str) -> dict | None:
    if not paths:
        return {"results": []}
    proc = subprocess.run(
        ["bandit", *paths, "--ini", ini, "-lll", "-f", "json"],
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        print("bandit produced no output while computing findings:", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        print("bandit produced unparseable JSON while computing findings:", file=sys.stderr)
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        return None


def flagged_line_text(result: dict) -> str:
    target = result.get("line_number")
    for line in result.get("code", "").splitlines():
        m = LINE_RE.match(line)
        if m and int(m.group(1)) == target:
            return " ".join(m.group(2).split())
    # Fall back to the whole code block if the line-number prefix format ever changes —
    # still strictly more conservative (harder to match, so more likely "new") than
    # silently treating an unparsed finding as pre-existing.
    return " ".join(result.get("code", "").split())


def finding_key(relative_path: str, result: dict) -> tuple[str, str, str]:
    return (relative_path, result.get("test_id", ""), flagged_line_text(result))


def collect_keys(data: dict, paths_to_relative: dict[str, str]) -> set[tuple[str, str, str]]:
    keys = set()
    for result in data.get("results", []):
        filename = result.get("filename", "")
        relative = paths_to_relative.get(filename, filename)
        keys.add(finding_key(relative, result))
    return keys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--ini", required=True)
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    if not args.files:
        print("No changed .py files passed to the baseline gate — nothing to compare.")
        return 0

    head_data = run_bandit_json(args.files, args.ini)
    if head_data is None:
        print("::error::Bandit failed to produce usable output for this PR's changed files — failing closed.")
        return 1
    head_keys = collect_keys(head_data, {f"./{f}": f for f in args.files} | {f: f for f in args.files})

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        baseline_paths: list[str] = []
        baseline_relative: dict[str, str] = {}
        for f in args.files:
            show = subprocess.run(
                ["git", "show", f"{args.base_ref}:{f}"],
                capture_output=True,
                text=True,
            )
            if show.returncode != 0:
                # File didn't exist at the base ref (new file this PR adds) — no baseline,
                # so every finding in it is correctly treated as new below.
                continue
            dest = tmp_root / f
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(show.stdout)
            baseline_paths.append(str(dest))
            baseline_relative[str(dest)] = f
            baseline_relative[f"./{dest}"] = f

        baseline_keys: set[tuple[str, str, str]] = set()
        if baseline_paths:
            baseline_data = run_bandit_json(baseline_paths, args.ini)
            if baseline_data is None:
                print("::error::Bandit failed to produce usable output for the base-ref baseline — failing closed.")
                return 1
            baseline_keys = collect_keys(baseline_data, baseline_relative)

    head_by_key = {}
    for result in head_data.get("results", []):
        filename = result.get("filename", "")
        relative = filename[2:] if filename.startswith("./") else filename
        head_by_key[finding_key(relative, result)] = result

    new_keys = head_keys - baseline_keys
    if not new_keys:
        print(f"Bandit: {len(head_keys)} finding(s) on changed files, all pre-existing at {args.base_ref}. Pass.")
        return 0

    print(f"Bandit: {len(new_keys)} NEW HIGH-severity finding(s) introduced by this PR:", file=sys.stderr)
    for key in sorted(new_keys):
        result = head_by_key.get(key)
        if result is None:
            continue
        print(
            f"  {result.get('filename')}:{result.get('line_number')} "
            f"{result.get('test_id')} {result.get('issue_text')}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
