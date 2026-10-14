#!/usr/bin/env python3
"""Check the four lane skills against a local agent-swarm main checkout.

The checkout is read-only evidence. Default path is /tmp/agent-swarm-main.
Set AGENT_SWARM_MAIN to point somewhere else. This script does not write there.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

PIN = "825a69918256c8cbe25e608aa44e52ea7272ae9d"
PR34 = "4e8d9e7aad51d291b0f1816bd29e78c79dc5956c"
HEADINGS = (
    "## v2.1 tool registry",
    "## Shared pool",
    "## In-process ACP",
    "## Commit-time registry drift gates",
    "## Cursor headless-runner ban",
    "## Keyless signing preflight",
    "## Pending merge",
)
LANES = {
    "control": {"A01"},
    "delivery": {"A02", "A03", "A04"},
    "verify": {"A08", "A09", "A10"},
    "sustain": {"A14", "A15"},
}
PENDING_TOKENS = (
    "PENDING MERGE — not on agent-swarm main.",
    PR34,
    "SPE-10696",
    "fix/signed-controller-bootstrap",
    "https://github.com/swcstudiospace/agent-swarm/pull/34",
)


def main() -> int:
    swarm = Path(os.environ.get("AGENT_SWARM_MAIN", "/tmp/agent-swarm-main"))
    repo = Path(__file__).resolve().parents[2]
    sha = subprocess.check_output(["git", "-C", str(swarm), "rev-parse", "HEAD"], text=True).strip()
    if sha != PIN:
        print(f"agent-swarm HEAD {sha} is not {PIN}", file=sys.stderr)
        return 1
    catalog = (swarm / "docs/tools/catalog.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([a-z0-9_]+)` \| ([A-Z0-9]+|shared) \|", catalog, re.M)
    owners = {name: owner for name, owner in rows}
    if len(owners) != 23:
        print(f"catalog has {len(owners)} tools, expected 23", file=sys.stderr)
        return 1
    preflight = (swarm / "scripts/swarm_run.py").read_text(encoding="utf-8")
    for lane, allowed in LANES.items():
        text = (repo / "grokbot/skills" / f"swarm-{lane}" / "SKILL.md").read_text(encoding="utf-8")
        section = text.split("Lane tools for this skill:", 1)[1].split("Shared pool for this skill:", 1)[0]
        first_col = set(re.findall(r"^\| `([a-z0-9_]+)` \|", section, re.M))
        expected = {name for name, owner in owners.items() if owner in allowed}
        if first_col != expected:
            print(lane, "missing", sorted(expected - first_col), "extra", sorted(first_col - expected), file=sys.stderr)
            return 1
        for heading in HEADINGS:
            if heading not in text:
                print(lane, "missing", heading, file=sys.stderr)
                return 1
        pending = text.split("## Pending merge", 1)[1]
        for token in PENDING_TOKENS:
            if token not in pending:
                print(lane, "pending section missing", token, file=sys.stderr)
                return 1
        if "fail-closed: no signing key configured" not in text:
            print(lane, "missing keyless preflight sentence", file=sys.stderr)
            return 1
        if "Do not start an unattended headless runner" not in text:
            print(lane, "missing headless-runner ban", file=sys.stderr)
            return 1
    if "fail-closed: no signing key configured" not in preflight:
        print("swarm_run.py has no keyless preflight sentence", file=sys.stderr)
        return 1
    print(
        "lane first-column tools match the 23-tool catalog; "
        "four skills carry the v2.1 headings and the pending-merge pin"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
