# C-3 · `loop_acks` has no gate, so a seat can approve its own degraded turn

**Owner:** bot-06-quality-security · **File:** `ci/gates/check_receipt.py`

## The defect

A degraded-mode turn ack — a human saying "work this ticket even though the memory brief failed" —
is recorded in the receipt's `loop_acks` (loop skill §3.1). Nothing reads that field. So a receipt
can carry an entry that looks complete and names **no human at all**:

```json
{ "condition": "brief_degraded",
  "operation": "degraded-loop: repo work without a memory brief",
  "ack_id": "ack-2026-09-30-004",
  "human_granted_by": "bot-00-programming-lead",   ← a seat, not a person
  "at": "2026-09-30T09:41:11Z",
  "scope": "one turn, one ticket" }
```

and pass CI. That is a degraded turn with no human in it, recorded as though it complied — worse
than a missing field, because it reads as compliance to anyone skimming. The whole value of the ack
is that a person who knew what the brief could not tell the seat said go ahead.

It cannot go in `approvals[]` to borrow G-6's validation: `check_rollback.py` validates every entry
there once a destructive command is present **and pairs entries to destructive operations by count**,
so a turn ack in `approvals[]` either fails a receipt whose destructive op was properly approved, or
silently satisfies G-6 for one nobody approved. The three committed fixtures in
[`../fixtures/`](../fixtures/README.md) demonstrate both directions and the correct shape.

**So the check belongs in G-2, and must not be added to G-6.** Anything `check_rollback.py` counts
can vouch for an `rm -rf` it never authorised.

## Patch

Constants beside `REQUIRED_FIELDS`:

```python
REQUIRED_LOOP_ACK_FIELDS = ["condition", "operation", "ack_id", "human_granted_by", "at", "scope"]
LOOP_ACK_CONDITIONS = {"brief_degraded", "brief_no_revision_marker"}
SEAT_ID_RE = re.compile(
    r"^\s*(?:bot-0[0-6](?:-[a-z0-9-]+)?|LEAD|SYSTEMS|WEB|ANDROID|IOS|INFRA|QUALITY|the desk)\s*$",
    re.IGNORECASE,
)
```

In `check()`, after the claims loop:

```python
loop_acks = receipt.get("loop_acks")
if loop_acks is not None:
    if not isinstance(loop_acks, list):
        problems.append("'loop_acks' must be a list")
    else:
        for i, ack in enumerate(loop_acks):
            if not isinstance(ack, dict):                     # ← the TypeError guard
                problems.append(f"loop_acks[{i}] must be an object")
                continue
            missing = [f for f in REQUIRED_LOOP_ACK_FIELDS if not ack.get(f)]
            if missing:
                problems.append(
                    f"loop_acks[{i}] is missing {missing} — a degraded-mode ack records the "
                    "condition, the operation, the ack id, the human who granted it, when, and "
                    "the one turn it covers")
            granter = str(ack.get("human_granted_by") or "")
            if granter and SEAT_ID_RE.match(granter):
                problems.append(
                    f"loop_acks[{i}] human_granted_by is {granter!r}, which is a seat, not a human "
                    "— degraded repo work needs a person's acknowledgement. The relaying seat goes "
                    "in 'relayed_by'")
            cond = ack.get("condition")
            if cond and cond not in LOOP_ACK_CONDITIONS:
                problems.append(f"loop_acks[{i}] condition {cond!r} is not one of "
                                f"{sorted(LOOP_ACK_CONDITIONS)}")
```

**The `isinstance` guard is not decoration.** Without it, `loop_acks: ["ack-123"]` — a plausible
mistake, a list of ids rather than of objects — reaches `ack.get` on a `str` and raises
`AttributeError` inside the gate. A gate that crashes on malformed input is a gate whose verdict
nobody gets, so the shape check comes before every field read. The same applies to `loop_acks`
itself not being a list.

Note `loop_acks` is **optional**: `receipt.get("loop_acks") is None` must stay a pass, or every
receipt on the desk that never ran a degraded turn starts failing.

## How to tell it worked

Three fixtures, committed, no setup:

```sh
F=skills/desk-bootstrap/desk-production-loop/fixtures
python3 ci/gates/check_receipt.py --receipt $F/loop-acks-valid.json          --bot bot-00-programming-lead   # 0
python3 ci/gates/check_receipt.py --receipt $F/loop-acks-seat-grantor.json   --bot bot-00-programming-lead   # 1, names the field
python3 ci/gates/check_receipt.py --receipt $F/loop-acks-missing-grantor.json --bot bot-00-programming-lead  # 1, names it missing
python3 ci/gates/check_receipt.py --receipt $F/loop-acks-malformed.json      --bot bot-00-programming-lead   # 1, must NOT traceback
```

`fixtures/check-loop-acks.py` in this repository already implements exactly these rules as a
standalone checker, and `verify.sh` runs it over all four fixtures. Porting it into G-2 should
reproduce its verdicts; if it does not, one of the two is wrong and the disagreement is the thing to
look at.

## Pairs with C-4

[C-4](./C-4-quality-receipt-contract.md) puts `loop_acks` in the shared receipt contract. A gate
enforcing a field the contract does not document would be a gate nobody can anticipate, so land them
together.
