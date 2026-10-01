#!/usr/bin/env python3
"""SPE-5715 opt-in live smoke: coord_drift_scan cases (b) expired-lease drift and (c)
tip/event disagreement, against a real substrate-mcp.

Not collected by pytest (no test_ prefix) and not run in CI, for the same reason
conftest.py strips every upstream credential from the default suite: this smoke needs a real
substrate-mcp behind SUBSTRATE_URL/SUBSTRATE_TOKEN, and must never run with whatever credential
happens to be ambient on a host.

Skip-clean (exit 0, printed SKIP line, no assertion attempted) only for not being opted in at
all: DESK_COORD_SMOKE_LIVE != 1, or SUBSTRATE_URL/SUBSTRATE_TOKEN unset — same opt-in shape as
PR #58's lease-cas-drift-smoke.py, same env names the gateway itself reads
(desk_gateway.config.Settings). Once opted in, every later problem — registration failing, the
claim not landing, a scan erroring, an expected finding never showing up — is a FAIL, not a
SKIP: a green run has to mean the two conditions below were actually exercised and observed,
not that something upstream quietly didn't cooperate (caught on review, PR #59).

    DESK_COORD_SMOKE_LIVE=1 SUBSTRATE_URL=... SUBSTRATE_TOKEN=... python3 \\
        services/desk-gateway/tests/fixtures/coordination-drift-smoke.py

Case (b), expired-lease drift, needs a lease actually to expire (ttl_seconds floors at 30 per
the substrate's own schema — SPE-4792), so this smoke sleeps past that floor rather than
fabricate the condition; it is slow by design, which is why it is opt-in and not part of the
default suite.

Case (c), tip/event disagreement, is asserted the honest way available without a second git
remote to diverge for real: coord_drift_scan is called with a git_tip that is not the repo's
actual tip, and the smoke requires a disagreement finding naming that mismatch — the substrate
decides what a mismatched tip means (DRIFT-SCAN.md §1.2), this smoke only requires that it says
something about it.

Out of scope, deliberately: case (a) exclusivity (two concurrent graph_claim calls, exactly one
holder) is PR #58's lease-cas-drift-smoke.py and is not duplicated here — this smoke only proves
what is specific to graph_heartbeat and coord_drift_scan.

Cleanup is unconditional once registration succeeds: every exit path below — pass, fail, or an
exception from a scan — runs through a `finally` that calls graph_complete on the fixture node.
An earlier revision only attempted a best-effort graph_release after both cases had already
passed, so a failed scan (or any case failing) left the registered graph/node behind with its
state still "open" — exactly the work.unclaimed shape a later, unrelated drift scan against a
shared substrate would then report (caught on review, PR #59).
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

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


class _Skip(Exception):
    """Not opted in, or opted in with nothing configured — exit 0, nothing was created yet."""


class _Fail(Exception):
    """Opted in and configured: a real problem. Exit 1."""


def _unwrap(result: dict[str, Any]) -> Any:
    content = result.get("content")
    return content[0] if isinstance(content, list) and content else content


def _findings(body: Any) -> list[dict]:
    if not isinstance(body, dict):
        return []
    findings = body.get("findings")
    return [f for f in findings if isinstance(f, dict)] if isinstance(findings, list) else []


def _unavailable(body: Any) -> list:
    if not isinstance(body, dict):
        return []
    unavailable = body.get("unavailable")
    return unavailable if isinstance(unavailable, list) else []


async def _run() -> None:
    if os.environ.get("DESK_COORD_SMOKE_LIVE") != "1":
        raise _Skip("DESK_COORD_SMOKE_LIVE is not set to 1 — this smoke needs a real substrate-mcp and does not run by default")
    if not os.environ.get("SUBSTRATE_URL") or not os.environ.get("SUBSTRATE_TOKEN"):
        raise _Skip("DESK_COORD_SMOKE_LIVE=1 but SUBSTRATE_URL / SUBSTRATE_TOKEN is not set — opted in with nothing to opt into")

    from desk_gateway.config import Settings
    from desk_gateway.upstreams import Substrate

    settings = Settings.from_env()
    substrate = Substrate(settings)
    if not substrate.configured:
        raise _Skip("Substrate reports not configured despite the env — check SUBSTRATE_URL/SUBSTRATE_TOKEN")

    # Opted in and configured past this point: every failure below is a FAIL, not a SKIP. A
    # setup step that silently skipped (as an earlier revision did on a failed graph_claim) lets
    # a broken registration or a stolen claim read as a clean, meaningless pass.
    graph_id = f"ut-spe5715coord-{uuid.uuid4().hex[:8]}"
    node_id = "n1"
    session_id = f"spe-5715-coord-smoke:{graph_id}"

    # --- setup: register the graph/node before claiming it -----------------------------
    # Same payload shape as lead.graph_register (services/desk-gateway/src/desk_gateway/tools/
    # lead.py), the one other place in this gateway that calls the substrate's graph_register.
    register = await substrate.call_tool(
        "graph_register",
        {
            "graph_id": graph_id,
            "repo": REPO,
            "status": "planning",
            "nodes": [{"node_id": node_id, "state": "open"}],
        },
        timeout=10,
    )
    if register.get("error"):
        raise _Fail(f"graph_register failed: {register.get('reason')} — without it graph_claim may be claiming a node "
                    "the substrate never heard of, which is not the condition this smoke is meant to test")

    # From here on, the fixture graph/node exists on the substrate. Nothing below may return or
    # raise without going through the `finally` in run(), which closes it out — see that
    # function's docstring note on why an earlier revision left these behind.
    try:
        # --- case (b): expired-lease drift ---------------------------------------------
        claim = await substrate.call_tool(
            "graph_claim",
            {"graph_id": graph_id, "node_id": node_id, "session_id": session_id, "ttl_seconds": MIN_TTL_SECONDS},
            timeout=10,
        )
        if claim.get("error"):
            raise _Fail(f"graph_claim failed: {claim.get('reason')} — this smoke needs a held lease to let expire")
        claimed = _unwrap(claim)
        if not isinstance(claimed, dict) or claimed.get("claimed") is False:
            raise _Fail(f"graph_claim did not report a held lease (another holder, or an unexpected shape): {claimed!r}")

        print(f"claimed {graph_id}/{node_id}, waiting {MIN_TTL_SECONDS + 5}s past the {MIN_TTL_SECONDS}s TTL with no heartbeat ...")
        time.sleep(MIN_TTL_SECONDS + 5)

        scan_b = await substrate.call_tool("coord_drift_scan", {"repo": REPO}, timeout=15)
        if scan_b.get("error"):
            raise _Fail(f"coord_drift_scan (case b) returned an error: {scan_b.get('reason')}")
        body_b = _unwrap(scan_b)
        findings_b = _findings(body_b)
        bad_kinds = {f.get("kind") for f in findings_b if f.get("kind") not in DRIFT_KINDS}
        if bad_kinds:
            raise _Fail(f"coord_drift_scan (case b) reported kind(s) outside the published DriftKind enum: {sorted(bad_kinds)}")
        # Filtered on graph_id AND node_id: node_id alone would also match an unrelated "n1"
        # under a different graph the substrate happens to be tracking.
        lease_findings = [
            f for f in findings_b
            if str(f.get("kind", "")).startswith("lease.") and f.get("graph_id") == graph_id and f.get("node_id") == node_id
        ]
        if not lease_findings:
            unavailable_b = _unavailable(body_b)
            if unavailable_b:
                raise _Fail(f"case (b): no lease.* finding for {graph_id}/{node_id} after the TTL, and the scan reports "
                            f"{unavailable_b!r} unavailable — inconclusive, not a demonstrated absence of drift")
            raise _Fail(f"case (b): no lease.* finding for {graph_id}/{node_id} {MIN_TTL_SECONDS + 5}s after an unrenewed "
                        f"{MIN_TTL_SECONDS}s-TTL claim — the condition was constructed and the scan reported itself "
                        "complete, so an expired lease should have surfaced")
        print(f"case (b) PASS: {[f['kind'] for f in lease_findings]} for {graph_id}/{node_id}")

        # --- case (c): tip/event disagreement -------------------------------------------
        fake_tip = "0" * 40
        scan_c = await substrate.call_tool("coord_drift_scan", {"repo": REPO, "git_tip": fake_tip}, timeout=15)
        if scan_c.get("error"):
            raise _Fail(f"coord_drift_scan (case c) returned an error: {scan_c.get('reason')}")
        body_c = _unwrap(scan_c)
        findings_c = _findings(body_c)
        bad_kinds_c = {f.get("kind") for f in findings_c if f.get("kind") not in DRIFT_KINDS}
        if bad_kinds_c:
            raise _Fail(f"coord_drift_scan (case c) reported kind(s) outside the published DriftKind enum: {sorted(bad_kinds_c)}")
        tip_findings = [f for f in findings_c if f.get("kind") in {"git.tip_unlogged", "ledger.commit_unknown_to_git"}]
        if not tip_findings:
            unavailable_c = _unavailable(body_c)
            if unavailable_c:
                raise _Fail(f"case (c): no tip-disagreement finding for a fabricated git_tip, and the scan reports "
                            f"{unavailable_c!r} unavailable — inconclusive, not a demonstrated absence of drift")
            raise _Fail(f"case (c): no tip-disagreement finding (git.tip_unlogged / ledger.commit_unknown_to_git) for "
                        f"git_tip={fake_tip!r}, which cannot be this repo's real tip — the condition was constructed "
                        "and the scan reported itself complete, so a disagreement should have surfaced")
        print(f"case (c) PASS: {[f['kind'] for f in tip_findings]}")
    finally:
        # Unconditional: runs whether the two cases above passed, raised _Fail, or raised
        # anything else (a timeout, a KeyError in a malformed response). graph_complete rather
        # than graph_release: release only drops the lease and leaves the node "open", which is
        # the unclaimed-work shape this cleanup exists to avoid, not fix.
        complete = await substrate.call_tool(
            "graph_complete",
            {"graph_id": graph_id, "node_id": node_id,
             "result": {"summary": "coordination-drift-smoke fixture cleanup", "tests_pass": True}},
            timeout=10,
        )
        if complete.get("error"):
            print(f"NOTE: cleanup graph_complete failed, not asserted: {complete.get('reason')} — "
                  f"{graph_id}/{node_id} may still read as open on a shared substrate")

    print("coordination-drift-smoke: done")


def main() -> int:
    try:
        asyncio.run(_run())
    except _Skip as exc:
        print(f"SKIP: {exc}")
        return 0
    except _Fail as exc:
        print(f"FAIL: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
