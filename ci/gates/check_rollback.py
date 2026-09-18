#!/usr/bin/env python3
"""Gates G-5 and G-6 — rollback plans and destructive operations.

G-5: no deployment without a rollback plan that names the command, the recovery time and the
     data implications. "We can roll back" is true of a deployment and frequently false of the
     system it deployed — a migration or a poisoned cache does not roll back with it.

G-6: destructive operations need explicit human approval recorded BEFORE execution, with the
     blast radius as understood at approval time.

    python3 ci/gates/check_rollback.py --receipt .receipts/deploy.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# (pattern, category, description)
DESTRUCTIVE_PATTERNS: list[tuple[str, str, str]] = [
    (r"\bterraform\s+destroy\b",                 "infra",   "destroys managed infrastructure"),
    (r"\bterraform\s+state\s+(?:rm|mv)\b",       "infra",   "mutates Terraform state"),
    (r"\bterraform\s+apply\b.*--auto-approve",   "infra",   "applies without a reviewed plan"),
    (r"\bkubectl\s+delete\b",                    "infra",   "deletes Kubernetes resources"),
    (r"\bkubectl\s+drain\b",                     "infra",   "evicts workloads from a node"),
    (r"\bhelm\s+(?:delete|uninstall)\b",         "infra",   "removes a release"),
    (r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA)\b",    "data",    "drops a database object"),
    (r"\bTRUNCATE\b",                            "data",    "empties a table"),
    (r"\bDELETE\s+FROM\b(?!.*\bWHERE\b)",        "data",    "unbounded delete"),
    (r"\bgit\s+push\b.*(?:--force|-f)\b",        "git",     "force push"),
    (r"\bgit\s+reset\s+--hard\b",                "git",     "discards work irrecoverably"),
    (r"\bgit\s+filter-(?:branch|repo)\b",        "git",     "rewrites history"),
    (r"\brm\s+-rf?\b",                           "fs",      "recursive delete"),
    (r"\bdocker\s+system\s+prune\b",             "fs",      "removes shared caches and volumes"),
    (r"\bdocker\s+volume\s+rm\b",                "fs",      "removes a volume"),
    (r"\baws\s+s3\s+rb\b",                       "data",    "removes a bucket"),
    (r"\baws\s+s3\s+rm\b.*--recursive",          "data",    "recursive object delete"),
    (r"\bmkfs\b",                                "fs",      "formats a filesystem"),
    (r"\bdd\s+.*of=/dev/",                       "fs",      "writes directly to a device"),
]

DEPLOY_PATTERNS = [
    r"\bvercel\s+(?:deploy|promote|--prod)\b",
    r"\bterraform\s+apply\b",
    r"\bkubectl\s+apply\b",
    r"\bkubectl\s+rollout\b",
    r"\bhelm\s+(?:install|upgrade)\b",
    r"\bfastlane\s+(?:deliver|pilot|supply)\b",
    r"\bgcloud\s+(?:app\s+deploy|run\s+deploy)\b",
    r"\baws\s+(?:deploy|ecs\s+update-service)\b",
]

REQUIRED_APPROVAL_FIELDS = ["operation", "approved_by", "at", "blast_radius"]

# A rollback plan must say more than "roll back".
PLAN_MIN_WORDS = 12
PLAN_SIGNALS = [
    (r"(?i)\b(?:command|run|via|using|`|\bvercel\b|\bkubectl\b|\bterraform\b|\bgit\b)",
     "the command or procedure"),
    # NOTE: \bsecond\b does not match "seconds" — the trailing \b lands mid-word.
    (r"(?i)(?:seconds?|minutes?|hours?|instant|immediate|~\s*\d|\d+\s*(?:s|m|min|h)\b)",
     "the expected recovery time"),
    (r"(?i)\b(?:data|schema|migration|cache|state|none|no data)\b",
     "the data implications"),
]


def load(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"check_rollback: no receipt at {path}")
    return json.loads(path.read_text())


def find_matches(commands: list, patterns) -> list[tuple[int, str, str, str]]:
    hits = []
    for i, cmd in enumerate(commands):
        cmd_str = cmd.get("cmd", "") if isinstance(cmd, dict) else str(cmd)
        for entry in patterns:
            if isinstance(entry, tuple):
                pattern, category, desc = entry
            else:
                pattern, category, desc = entry, "deploy", "deployment"
            if re.search(pattern, cmd_str):
                hits.append((i, cmd_str, category, desc))
    return hits


def check_plan(plan: str | None) -> list[str]:
    if not plan or not str(plan).strip():
        return ["rollback_plan is empty"]

    problems = []
    text = str(plan)

    if len(text.split()) < PLAN_MIN_WORDS:
        problems.append(
            f"rollback_plan is {len(text.split())} words — too short to name a command, "
            f"a recovery time and the data implications"
        )

    for pattern, what in PLAN_SIGNALS:
        if not re.search(pattern, text):
            problems.append(f"rollback_plan does not state {what}")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Gates G-5/G-6: rollback and destructive ops")
    ap.add_argument("--receipt", type=Path, required=True)
    args = ap.parse_args()

    receipt = load(args.receipt)
    commands = receipt.get("commands", [])
    approvals = receipt.get("approvals", []) or []
    problems: list[str] = []

    # --- G-6: destructive operations --------------------------------------
    destructive = find_matches(commands, DESTRUCTIVE_PATTERNS)
    if destructive:
        print(f"G-6 — {len(destructive)} destructive operation(s) detected:")
        for idx, cmd, category, desc in destructive:
            print(f"    [{idx}] ({category}) {cmd}")
            print(f"         {desc}")

        if not approvals:
            problems.append(
                "destructive operations with NO approvals recorded.\n"
                "      These require explicit human approval BEFORE execution (G-6)."
            )
        else:
            for i, ap_rec in enumerate(approvals):
                missing = [f for f in REQUIRED_APPROVAL_FIELDS if not ap_rec.get(f)]
                if missing:
                    problems.append(
                        f"approvals[{i}] is missing {missing} — an approval records what was "
                        "approved, by whom, when, and the blast radius"
                    )
            if len(approvals) < len(destructive):
                problems.append(
                    f"{len(destructive)} destructive operation(s) but only {len(approvals)} "
                    "approval(s) — each needs its own"
                )

    # --- G-5: deployments need a rollback plan ----------------------------
    deploys = find_matches(commands, DEPLOY_PATTERNS)
    if deploys:
        print(f"G-5 — {len(deploys)} deployment command(s) detected:")
        for idx, cmd, _cat, _desc in deploys:
            print(f"    [{idx}] {cmd}")

        plan_problems = check_plan(receipt.get("rollback_plan"))
        for p in plan_problems:
            problems.append(f"G-5: {p}")

    if problems:
        print("\nG-5/G-6 FAIL", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\n  See docs/quality-gates.md G-5 and G-6", file=sys.stderr)
        return 1

    if not destructive and not deploys:
        print("G-5/G-6 PASS — no deployments or destructive operations in this receipt")
    else:
        print(f"\nG-5/G-6 PASS — {len(deploys)} deployment(s) with a rollback plan, "
              f"{len(destructive)} destructive op(s) approved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
