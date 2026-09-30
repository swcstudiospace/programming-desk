#!/usr/bin/env python3
"""SPE-5715 exclusivity smoke — the only one of the three requested cases this repo can run.

Case (a), two concurrent claimants -> exactly one holder. Cases (b) (expired-lease drift) and
(c) (tip/event disagreement) are not implemented here because neither a lease-heartbeat renewal
tool nor `coord.drift_scan` exists anywhere in this repository or its docs to call — see the
"SPE-5715" section appended to `skills/desk-bootstrap/desk-production-loop/SKILL.md` for the
file-by-file evidence. Faking either call, or inventing a drift-kind name to assert against, would
prove nothing and would violate this ticket's own instruction not to guess substrate facts.

Live and gated on purpose. `graph_claim` / `graph_release` / `graph_complete` are real substrate-mcp
tools, already wired (not stubbed) in `services/desk-gateway/src/desk_gateway/tools/lead.py`'s
`graph_state`. A mocked "exclusivity" here would only re-assert a mock's own return value, never
substrate's actual compare-and-set — that is provable only against a live substrate-mcp, which
needs a real bearer token. So this script is opt-in, is not part of any default test run, and never
runs off ambient credentials alone: `services/desk-gateway/tests/conftest.py` deliberately isolates
tests from ambient upstream env vars for the same reason, and this script follows that convention
by requiring an explicit opt-in on top of the credential.

Requires ALL of the following. Only `DESK_LEASE_SMOKE_LIVE` unset is a clean **SKIP** (exit 0,
reason printed, never a silent pass and never a hang) — that is the sole "never asked to run at
all" case. Once `DESK_LEASE_SMOKE_LIVE=1` is set, every other missing or broken precondition
(`SUBSTRATE_URL`, `SUBSTRATE_TOKEN`, an unimportable gateway package, `Substrate.configured` still
false, or any unexpected exception in the live body) is a **FAIL** (exit 1), never a skip: a run
that explicitly asked to go live and could not must not report the same clean exit as a run that
never asked to run at all.

    DESK_LEASE_SMOKE_LIVE=1     explicit opt-in; the other two vars alone are not enough
    SUBSTRATE_URL               e.g. http://127.0.0.1:7410 -- must be set explicitly. Settings
                                 defaults this to the loopback address even when unset, so without
                                 this separate check a live-opt-in run with only SUBSTRATE_TOKEN set
                                 would silently target that default instead of skipping.
    SUBSTRATE_TOKEN             a bearer valid for that substrate-mcp

Never pass the token on a command line where it would be visible in `ps`; export it instead. This
script reads it only from the environment and never logs it or any header.

    DESK_LEASE_SMOKE_LIVE=1 SUBSTRATE_URL=http://127.0.0.1:7410 SUBSTRATE_TOKEN=*** \\
      python3 skills/desk-bootstrap/desk-production-loop/fixtures/lease-cas-drift-smoke.py

Unverified assumption, stated here rather than hidden: this script treats a CAS conflict on
`graph_claim` as surfacing through the generic MCP wrapper's `error`/`is_error` (as every other
`Substrate.call_tool` result does in `services/desk-gateway/src/desk_gateway/upstreams.py`), not as
an `ok: true` response carrying a nested "not claimed" verdict. Nothing in this repository confirms
which shape substrate actually returns on a conflict — `agent-substrate` is out of this session's
read access. Because of that, a losing call whose error is specifically `upstream_timeout`
(`UPSTREAM_TIMEOUT` in `upstreams.py`) is treated as **inconclusive, not proof**: a timeout means the
call may never have reached CAS at all, which is a transport failure, not a refusal. Only a losing
call that reports `upstream_error` (the tool actually ran and reported failure, or returned a
non-2xx/JSON-RPC error) is treated as a genuine CAS refusal. On any outcome this script cannot
classify cleanly, it prints both raw results and exits 1 rather than guessing which one held the
lease.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GATEWAY_SRC = ROOT / "services" / "desk-gateway" / "src"

# The desk's own uplift/intake pipeline documents nodeId values as n1, n2, ... (see
# docs/intake-e2e-runbook.md, docs/gotxcot-cloud-pipeline.md). Claiming an id in that shape, and
# registering it on the graph first, keeps this smoke's claim call shaped like a real production
# claim rather than an arbitrary string a stricter substrate build might reject for an unrelated
# reason (unknown node) before CAS is ever exercised.
NODE_ID = "n1"


def _skip(reason: str) -> None:
    print(f"SKIP: {reason}")
    sys.exit(0)


def _fail(reason: str) -> None:
    print(f"FAIL: {reason}")
    sys.exit(1)


async def _release_best_effort(substrate: "Substrate", graph_id: str, session_id: str, label: str) -> None:
    """Best-effort cleanup for a claim that may have gone through. Never raises; always reports."""
    result = await substrate.call_tool(
        "graph_release", {"graph_id": graph_id, "node_id": NODE_ID, "session_id": session_id}
    )
    if result.get("error"):
        print(f"note: cleanup graph_release for {label} did not succeed (does not change the verdict above): {result}")


async def _run() -> int:
    if os.environ.get("DESK_LEASE_SMOKE_LIVE", "").strip().lower() not in {"1", "true", "yes"}:
        _skip(
            "DESK_LEASE_SMOKE_LIVE is not set to 1 -- this smoke only runs opt-in against a live "
            "substrate-mcp, never off ambient credentials alone"
        )
    # From here on, live execution was explicitly requested: any further missing prerequisite is a
    # FAIL, not a skip, so an automated run cannot finish "successfully" without attempting a claim.
    if not os.environ.get("SUBSTRATE_TOKEN", "").strip():
        _fail("SUBSTRATE_TOKEN is unset -- no live substrate-mcp to prove exclusivity against")
    if not os.environ.get("SUBSTRATE_URL", "").strip():
        _fail(
            "SUBSTRATE_URL is unset -- Settings defaults this to the loopback address, which would "
            "target a real endpoint silently instead of failing closed; set it explicitly"
        )

    # Once live execution is explicitly requested, any further problem -- a missing dependency
    # (desk_gateway's own imports, or a package it lazily imports such as `mcp`), a network error,
    # an unexpected response shape -- is a FAIL, never an unhandled traceback and never a silent
    # skip. _fail()/_skip() raise SystemExit, which this does not catch, so an intentional exit
    # from inside the body below still exits with that code.
    try:
        return await _run_live()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 -- deliberately broad: see comment above
        _fail(f"unexpected error during the live smoke, not a controlled outcome: {exc!r}")
        return 1  # unreachable; _fail exits


async def _run_live() -> int:
    sys.path.insert(0, str(GATEWAY_SRC))
    try:
        from desk_gateway.config import Settings
        from desk_gateway.upstreams import Substrate
    except ImportError as exc:
        _fail(f"could not import desk_gateway from {GATEWAY_SRC} ({exc}) -- run from a checkout with the gateway package installed")
        return 1  # unreachable; _fail exits

    settings = Settings.from_env()
    substrate = Substrate(settings)
    if not substrate.configured:
        _fail("Substrate.configured is False despite SUBSTRATE_URL and SUBSTRATE_TOKEN both being set")

    graph_id = f"ut-spe5715smoke-{uuid.uuid4().hex[:8]}"
    repo = "swcstudiospace/programming-desk"

    reg = await substrate.call_tool(
        "graph_register",
        {"graph_id": graph_id, "repo": repo, "status": "planning", "nodes": [{"node_id": NODE_ID}]},
    )
    if reg.get("error"):
        _fail(f"graph_register did not succeed: {reg}")

    session_a = f"grok-bot:smoke-a:{graph_id}"
    session_b = f"grok-bot:smoke-b:{graph_id}"
    payload_a = {"graph_id": graph_id, "node_id": NODE_ID, "session_id": session_a}
    payload_b = {"graph_id": graph_id, "node_id": NODE_ID, "session_id": session_b}

    # Fired concurrently, not sequentially: a sequential pair proves only that the second caller
    # saw the first caller's write after the fact, never that CAS holds under real contention.
    result_a, result_b = await asyncio.gather(
        substrate.call_tool("graph_claim", payload_a),
        substrate.call_tool("graph_claim", payload_b),
    )

    # See the module docstring's "Unverified assumption" note before trusting this check on a
    # substrate whose conflict shape has never been observed from this session.
    ok_a = bool(result_a.get("ok")) and not result_a.get("error")
    ok_b = bool(result_b.get("ok")) and not result_b.get("error")

    if ok_a and ok_b:
        print(f"FAIL: both claimants succeeded -- exclusivity violated.\n  a={result_a}\n  b={result_b}")
        await _release_best_effort(substrate, graph_id, session_a, "claimant a (violation cleanup)")
        await _release_best_effort(substrate, graph_id, session_b, "claimant b (violation cleanup)")
        return 1
    if not ok_a and not ok_b:
        _fail(
            "neither claimant succeeded -- cannot tell whether exclusivity held or the substrate "
            f"was simply unreachable.\n  a={result_a}\n  b={result_b}"
        )

    holder, holder_result, holder_session = ("a", result_a, session_a) if ok_a else ("b", result_b, session_b)
    loser_result = result_b if ok_a else result_a

    # A losing call that timed out never demonstrably reached CAS at all -- that is a transport
    # failure, not a refusal, and reporting it as proof of exclusivity would be the exact defect
    # this script exists to avoid repeating at one remove.
    if loser_result.get("error") == "upstream_timeout":
        _fail(
            "one claimant succeeded but the other's graph_claim timed out rather than being refused "
            f"-- inconclusive, not proof of CAS exclusivity.\n  holder={holder_result}\n  timed_out={loser_result}"
        )

    print(
        f"OK: exactly one claimant ({holder}) holds graph_id={graph_id} node_id={NODE_ID}; "
        f"the other was refused by the tool, not merely timed out.\n  holder={holder_result}\n  refused={loser_result}"
    )

    cleanup = await substrate.call_tool(
        "graph_complete",
        {
            "graph_id": graph_id,
            "node_id": NODE_ID,
            "session_id": holder_session,
            "result": {"summary": "SPE-5715 exclusivity smoke cleanup", "tests_pass": True},
        },
    )
    if cleanup.get("error"):
        print(f"note: cleanup graph_complete for the holder did not succeed (does not change the verdict above): {cleanup}")
        await _release_best_effort(substrate, graph_id, holder_session, "holder (graph_complete failed)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
