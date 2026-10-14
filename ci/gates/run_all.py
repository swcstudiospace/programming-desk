#!/usr/bin/env python3
"""Run every gate. The single entry point for CI and for local pre-flight.

    python3 ci/gates/run_all.py --bot bot-03-android --base origin/main \
        --receipt .receipts/feat-push.json
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

GATES_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATES_DIR.parents[1]


def run(name: str, argv: list[str]) -> tuple[str, int]:
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
    result = subprocess.run([sys.executable, *argv], cwd=REPO_ROOT)
    return name, result.returncode


def discover_change_document(paths: list[str]) -> str | None:
    """Return the change document when ``paths`` contains exactly one.

    The gates workflow passes ``--change`` for a yaml under ``contracts/changes``.
    ``run_all`` used to ignore that and fail G-4 unless the caller repeated the
    path. Zero documents, or more than one, returns None so the caller does not
    guess among several.
    """
    docs = [
        path for path in paths
        if path.startswith("contracts/changes/") and path.endswith((".yaml", ".yml"))
    ]
    if len(docs) == 1:
        return docs[0]
    return None


def changed_change_documents(base: str) -> list[str]:
    """Yaml files under contracts/changes in ``base...HEAD``, excluding deletions.

    Same diff the gates workflow uses (``--diff-filter=d``). A missing base or a
    failed git call returns an empty list; G-4 then runs without ``--change`` and
    reports its own failure.
    """
    out = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=d", f"{base}...HEAD", "--", "contracts/changes"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if out.returncode != 0:
        print(out.stderr.strip() or "run_all: could not list contracts/changes", file=sys.stderr)
        return []
    return [line for line in out.stdout.splitlines() if line.endswith((".yaml", ".yml"))]


def main() -> int:
    ap = argparse.ArgumentParser(description="Run all quality gates")
    ap.add_argument("--bot", required=True)
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--change", type=Path, help="Contract change document, if any")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    results: list[tuple[str, int]] = []

    results.append(run(
        "G-1  Path ownership",
        [str(GATES_DIR / "check_ownership.py"), "--bot", args.bot, "--base", args.base],
    ))

    receipt_argv = [str(GATES_DIR / "check_receipt.py"),
                    "--receipt", str(args.receipt), "--bot", args.bot]
    if args.strict:
        receipt_argv.append("--strict")
    results.append(run("G-2  Verification receipt", receipt_argv))

    results.append(run(
        "G-3  Committed secrets",
        [str(GATES_DIR / "check_secrets.py"), "--base", args.base],
    ))

    contracts_argv = [str(GATES_DIR / "check_contracts.py"), "--base", args.base]
    change = args.change
    if change is None:
        docs = changed_change_documents(args.base)
        found = discover_change_document(docs)
        if found:
            print(f"G-4 change document: {found}")
            change = Path(found)
        elif len(docs) > 1:
            print(
                "G-4: more than one change document in the diff; pass --change. Not guessing.",
                file=sys.stderr,
            )
            for doc in docs:
                print(f"  {doc}", file=sys.stderr)
    if change is not None:
        contracts_argv += ["--change", str(change)]
    results.append(run("G-4  Contract-first changes", contracts_argv))

    results.append(run(
        "G-5/G-6  Rollback and destructive ops",
        [str(GATES_DIR / "check_rollback.py"), "--receipt", str(args.receipt)],
    ))

    # G-7 reads the repo as it is rather than a diff or a receipt, so it takes no --bot and
    # always runs: a bad roster is bad on every commit, not only the one that introduced it.
    results.append(run(
        "G-7  Desk integrity",
        [str(GATES_DIR / "check_desk_integrity.py"), "--repo", str(REPO_ROOT)],
    ))

    print(f"\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    failed = 0
    for name, code in results:
        status = "PASS" if code == 0 else "FAIL"
        if code != 0:
            failed += 1
        print(f"  [{status}]  {name}")

    if failed:
        print(f"\n{failed} gate(s) failed. Fix the cause — never bypass a gate (PD-3).")
        return 1

    print("\nAll gates passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
