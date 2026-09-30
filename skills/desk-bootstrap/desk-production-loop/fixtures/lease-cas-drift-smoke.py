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

Requires ALL of the following, or the run skips cleanly — exit 0, reason printed, never a silent
pass and never a hang:

    DESK_LEASE_SMOKE_LIVE=1     explicit opt-in; the other two vars alone are not enough
    SUBSTRATE_URL               e.g. http://127.0.0.1:7410 (same name the gateway itself reads)
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
read access — so on any outcome other than "exactly one ok, one error" this script prints both raw
results and exits 1 rather than guessing which one held the lease.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
GATEWAY_SRC = ROOT / "services" / "desk-gateway" / "src"


def _skip(reason: str) -> None:
    print(f"SKIP: {reason}")
    sys.exit(0)


async def _run() -> int:
    if os.environ.get("DESK_LEASE_SMOKE_LIVE", "").strip().lower() not in {"1", "true", "yes"}:
        _skip(
            "DESK_LEASE_SMOKE_LIVE is not set to 1 -- this smoke only runs opt-in against a live "
            "substrate-mcp, never off ambient credentials alone"
        )
    if not os.environ.get("SUBSTRATE_TOKEN", "").strip():
        _skip("SUBSTRATE_TOKEN is unset -- no live substrate-mcp to prove exclusivity against")

    sys.path.insert(0, str(GATEWAY_SRC))
    try:
        from desk_gateway.config import Settings
        from desk_gateway.upstreams import Substrate
    except ImportError as exc:
        _skip(f"could not import desk_gateway from {GATEWAY_SRC} ({exc}) -- run from a checkout with the gateway package installed")
        return 0  # unreachable; _skip exits

    settings = Settings.from_env()
    substrate = Substrate(settings)
    if not substrate.configured:
        _skip(
            "Substrate.configured is False despite the required env vars -- SUBSTRATE_URL is "
            "likely still the loopback default with no reachable substrate-mcp behind it"
        )

    graph_id = f"ut-spe5715smoke-{uuid.uuid4().hex[:8]}"
    node_id = "smoke-node-1"
    repo = "swcstudiospace/programming-desk"

    reg = await substrate.call_tool("graph_register", {"graph_id": graph_id, "repo": repo, "status": "planning"})
    if reg.get("error"):
        print(f"FAIL: graph_register did not succeed: {reg}")
        return 1

    session_a = f"grok-bot:smoke-a:{graph_id}"
    session_b = f"grok-bot:smoke-b:{graph_id}"
    payload_a = {"graph_id": graph_id, "node_id": node_id, "session_id": session_a}
    payload_b = {"graph_id": graph_id, "node_id": node_id, "session_id": session_b}

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
        return 1
    if not ok_a and not ok_b:
        print(
            "FAIL: neither claimant succeeded -- cannot tell whether exclusivity held or the "
            f"substrate was simply unreachable.\n  a={result_a}\n  b={result_b}"
        )
        return 1

    holder, holder_result, loser_result = ("a", result_a, result_b) if ok_a else ("b", result_b, result_a)
    print(
        f"OK: exactly one claimant ({holder}) holds graph_id={graph_id} node_id={node_id}; "
        f"the other was refused deterministically.\n  holder={holder_result}\n  refused={loser_result}"
    )

    winner_session = session_a if holder == "a" else session_b
    cleanup = await substrate.call_tool(
        "graph_complete",
        {
            "graph_id": graph_id,
            "node_id": node_id,
            "session_id": winner_session,
            "result": {"summary": "SPE-5715 exclusivity smoke cleanup", "tests_pass": True},
        },
    )
    if cleanup.get("error"):
        print(f"note: cleanup graph_complete did not succeed (does not change the verdict above): {cleanup}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
