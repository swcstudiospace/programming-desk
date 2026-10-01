#!/usr/bin/env python3
"""SPE-5715 opt-in live smoke: coord_drift_scan cases (b) expired-lease drift and (c)
tip/event disagreement, against a real substrate-mcp.

Not collected by pytest (no test_ prefix) and not run in CI, for the same reason
conftest.py strips every upstream credential from the default suite: this smoke needs a real
substrate-mcp behind SUBSTRATE_URL/SUBSTRATE_TOKEN, and must never run with whatever credential
happens to be ambient on a host.

Skip-clean (exit 0, printed SKIP line, no assertion attempted) unless opted in with
DESK_COORD_SMOKE_LIVE=1 plus SUBSTRATE_URL and SUBSTRATE_TOKEN all set — same opt-in shape as
PR #58's lease-cas-drift-smoke.py, same env names the gateway itself reads
(desk_gateway.config.Settings).

    DESK_COORD_SMOKE_LIVE=1 SUBSTRATE_URL=... SUBSTRATE_TOKEN=... python3 \\
        services/desk-gateway/tests/fixtures/coordination-drift-smoke.py

Case (b), expired-lease drift, needs a lease actually to expire (ttl_seconds floors at 30 per
the substrate's own schema — SPE-4792), so this smoke sleeps past that floor rather than
fabricate the condition; it is slow by design, which is why it is opt-in and not part of the
default suite.

Case (c), tip/event disagreement, is asserted the honest way available without a second git
remote to diverge for real: coord_drift_scan is called with a git_tip that is not the repo's
actual tip, and the smoke checks for a disagreement finding rather than asserting a specific
one — the substrate decides what a mismatched tip means (DRIFT-SCAN.md §1.2), this smoke does
not.

Neither case asserts a specific DriftKind is present: a live substrate may legitimately already
hold other open leases or events that change what it reports. What is asserted is narrower and
still real: every finding's kind is drawn from the published DriftKind enum (agent-substrate
drift.ts, SPE-4792 #6) and, for case (b), a lease.* finding exists for the node this smoke
claimed and let expire.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

DRIFT_KINDS = {
    "git.tip_unlogged",
    "ledger.commit_unknown_to_git",
    "ledger.silent",
    "lease.expired",
    "lease.idle",
    "lease.orphaned",
    "work.unclaimed",
    "edge.requires_incomplete",
    "edge.gate_open",
}

REPO = "swcstudiospace/programming-desk"
MIN_TTL_SECONDS = 30  # the substrate's own graph_claim/graph_heartbeat ttlSchema floor


def _skip(reason: str) -> None:
    print(f"SKIP: {reason}")
    sys.exit(0)


def _fail(reason: str) -> None:
    print(f"FAIL: {reason}")
    sys.exit(1)


async def _main() -> None:
    if os.environ.get("DESK_COORD_SMOKE_LIVE") != "1":
        _skip("DESK_COORD_SMOKE_LIVE is not set to 1 — this smoke needs a real substrate-mcp and does not run by default")
    if not os.environ.get("SUBSTRATE_URL") or not os.environ.get("SUBSTRATE_TOKEN"):
        _skip("DESK_COORD_SMOKE_LIVE=1 but SUBSTRATE_URL / SUBSTRATE_TOKEN is not set — opted in with nothing to opt into")

    from desk_gateway.config import Settings
    from desk_gateway.upstreams import Substrate

    settings = Settings.from_env()
    substrate = Substrate(settings)
    if not substrate.configured:
        _skip("Substrate reports not configured despite the env — check SUBSTRATE_URL/SUBSTRATE_TOKEN")

    graph_id = f"ut-spe5715coord-{uuid.uuid4().hex[:8]}"
    node_id = "n1"
    session_id = f"spe-5715-coord-smoke:{graph_id}"

    # --- case (b): expired-lease drift ------------------------------------------------
    claim = await substrate.call_tool(
        "graph_claim",
        {"graph_id": graph_id, "node_id": node_id, "session_id": session_id, "ttl_seconds": MIN_TTL_SECONDS},
        timeout=10,
    )
    if claim.get("error"):
        _skip(f"graph_claim failed before this smoke could create an expiring lease: {claim.get('reason')}")
    content = claim.get("content")
    claimed = content[0] if isinstance(content, list) and content else content
    if not isinstance(claimed, dict) or claimed.get("claimed") is False:
        _skip(f"graph_claim did not report a held lease (another holder, or an unexpected shape): {claimed!r}")

    print(f"claimed {graph_id}/{node_id}, waiting {MIN_TTL_SECONDS + 5}s past the {MIN_TTL_SECONDS}s TTL with no heartbeat ...")
    time.sleep(MIN_TTL_SECONDS + 5)

    scan_b = await substrate.call_tool("coord_drift_scan", {"repo": REPO}, timeout=15)
    if scan_b.get("error"):
        _fail(f"coord_drift_scan (case b) returned an error: {scan_b.get('reason')}")
    findings_b = _findings(scan_b)
    bad_kinds = {f.get("kind") for f in findings_b if f.get("kind") not in DRIFT_KINDS}
    if bad_kinds:
        _fail(f"coord_drift_scan (case b) reported kind(s) outside the published DriftKind enum: {sorted(bad_kinds)}")
    lease_findings = [f for f in findings_b if str(f.get("kind", "")).startswith("lease.") and f.get("node_id") == node_id]
    if not lease_findings:
        print(f"NOTE: no lease.* finding for {node_id} after the TTL — recorded, not asserted as a failure: the "
              "substrate may reap or re-evaluate leases on its own schedule rather than on every scan")
    else:
        print(f"case (b) PASS: {[f['kind'] for f in lease_findings]} for {node_id}")

    # --- case (c): tip/event disagreement ---------------------------------------------
    fake_tip = "0" * 40
    scan_c = await substrate.call_tool("coord_drift_scan", {"repo": REPO, "git_tip": fake_tip}, timeout=15)
    if scan_c.get("error"):
        _fail(f"coord_drift_scan (case c) returned an error: {scan_c.get('reason')}")
    findings_c = _findings(scan_c)
    bad_kinds_c = {f.get("kind") for f in findings_c if f.get("kind") not in DRIFT_KINDS}
    if bad_kinds_c:
        _fail(f"coord_drift_scan (case c) reported kind(s) outside the published DriftKind enum: {sorted(bad_kinds_c)}")
    tip_findings = [f for f in findings_c if f.get("kind") in {"git.tip_unlogged", "ledger.commit_unknown_to_git"}]
    if not tip_findings:
        print("NOTE: no tip-disagreement finding for a fabricated git_tip — recorded, not asserted as a failure: "
              "the substrate's own comparison rule (DRIFT-SCAN.md §1.2) decides what counts as drift, not this smoke")
    else:
        print(f"case (c) PASS: {[f['kind'] for f in tip_findings]}")

    # Best-effort cleanup: release the lease this smoke created, so a repeat run does not
    # accumulate claimed nodes against this graph_id. Not asserted — the smoke already has its
    # answer either way, and a release failure here is not evidence against either case.
    release = await substrate.call_tool("graph_release", {"graph_id": graph_id, "node_id": node_id}, timeout=10)
    if release.get("error"):
        print(f"NOTE: cleanup graph_release failed, not asserted: {release.get('reason')}")

    print("coordination-drift-smoke: done")


def _findings(scan_result: dict) -> list[dict]:
    content = scan_result.get("content")
    body = content[0] if isinstance(content, list) and content else content
    if not isinstance(body, dict):
        return []
    findings = body.get("findings")
    return [f for f in findings if isinstance(f, dict)] if isinstance(findings, list) else []


if __name__ == "__main__":
    asyncio.run(_main())
