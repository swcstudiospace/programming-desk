#!/usr/bin/env python3
"""Check the `loop_acks` shape in a receipt — the degraded-mode turn acknowledgements.

This is the LEAD-owned stand-in for a gate that does not exist yet. The rules it applies are
`skills/desk-bootstrap/desk-production-loop/SKILL.md` §3.1, and they belong in G-2
(`ci/gates/check_receipt.py`), which is bot-06-quality-security's — see
`../companion-patches/C-3-quality-loop-acks-g2.md` for the patch. Until that lands, CI does not
check `loop_acks` at all; this script is what makes the rule executable rather than prose, and it
is what the receipt's acknowledgement claims cite.

It is deliberately NOT in `ci/gates/`: a LEAD PR cannot add a gate, and a script under this skill
that anyone can run is honest about being a stand-in in a way a gate would not be.

**Why the check is G-2's and not G-6's.** `ci/gates/check_rollback.py` validates every `approvals`
entry once a destructive command is present, and pairs approvals to destructive operations *by
count*. Anything it counts can therefore vouch for an `rm -rf` it never authorised, so a turn ack
must never be visible to it. That is the whole reason `loop_acks` is a separate field.

    python3 skills/desk-bootstrap/desk-production-loop/fixtures/check-loop-acks.py RECEIPT...

Exit 0 when every receipt's `loop_acks` is well formed (or absent — the field is optional), 1
otherwise. Never tracebacks on malformed input: a checker that crashes gives no verdict, which is
worse than one that says no.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REQUIRED_FIELDS = ["condition", "operation", "ack_id", "human_granted_by", "at", "scope"]
CONDITIONS = {"brief_degraded", "brief_no_revision_marker"}

# Anything naming a seat rather than a person: the bot ids and the seat labels they go by. This is
# a denylist, so it raises the cost of recording a seat as the grantor — it cannot prove a string
# names a real human. That limit is recorded in the receipt's `unverified`.
SEAT_ID_RE = re.compile(
    r"^\s*(?:bot-0[0-6](?:-[a-z0-9-]+)?|LEAD|SYSTEMS|WEB|ANDROID|IOS|INFRA|QUALITY|the desk)\s*$",
    re.IGNORECASE,
)


def check_receipt(path: Path) -> list[str]:
    """Problems with one receipt's loop_acks. Empty list means well formed."""
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [f"cannot read {path}: {exc}"]
    except json.JSONDecodeError as exc:
        return [f"{path} is not valid JSON: {exc}"]
    if not isinstance(receipt, dict):
        return [f"{path} is not a JSON object"]

    acks = receipt.get("loop_acks")
    if acks is None:
        return []  # optional: a turn that never went degraded records nothing
    if not isinstance(acks, list):
        return [f"'loop_acks' must be a list, got {type(acks).__name__}"]

    problems: list[str] = []
    for i, ack in enumerate(acks):
        # Shape before fields, always. `loop_acks: ["ack-123"]` is a plausible mistake, and reaching
        # .get() on a str raises AttributeError inside the checker instead of reporting the defect.
        if not isinstance(ack, dict):
            problems.append(
                f"loop_acks[{i}] must be an object, got {type(ack).__name__} — a turn ack records "
                "six fields, not just an id"
            )
            continue

        missing = [f for f in REQUIRED_FIELDS if not ack.get(f)]
        if missing:
            problems.append(
                f"loop_acks[{i}] is missing {missing} — a degraded-mode ack records the condition, "
                "the operation, the ack id, the human who granted it, when, and the one turn it covers"
            )

        granter = ack.get("human_granted_by")
        if granter is not None and not isinstance(granter, str):
            problems.append(f"loop_acks[{i}] human_granted_by must be a string")
        elif granter and SEAT_ID_RE.match(granter):
            problems.append(
                f"loop_acks[{i}] human_granted_by is {granter!r}, which is a seat, not a human — "
                "degraded repo work needs a person's acknowledgement. The relaying seat goes in "
                "'relayed_by'"
            )

        cond = ack.get("condition")
        if cond and cond not in CONDITIONS:
            problems.append(
                f"loop_acks[{i}] condition {cond!r} is not one of {sorted(CONDITIONS)}"
            )

        relay = ack.get("relayed_by")
        if relay is not None and not isinstance(relay, str):
            problems.append(f"loop_acks[{i}] relayed_by must be a string or null")

    return problems


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: check-loop-acks.py RECEIPT...", file=sys.stderr)
        return 2

    failed = 0
    for arg in argv:
        path = Path(arg)
        problems = check_receipt(path)
        if problems:
            failed += 1
            print(f"FAIL: {path}", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
        else:
            acks = 0
            try:
                acks = len(json.loads(path.read_text(encoding="utf-8")).get("loop_acks") or [])
            except Exception:  # already reported as a problem above if it mattered
                pass
            print(f"ok: {path} — {acks} loop_acks entr{'y' if acks == 1 else 'ies'}, well formed")

    if failed:
        print(
            f"\nloop_acks FAIL — {failed} of {len(argv)} receipt(s).\n"
            "  See skills/desk-bootstrap/desk-production-loop/SKILL.md §3.1. CI does not check this "
            "yet; the G-2 patch is in companion-patches/C-3-quality-loop-acks-g2.md.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
