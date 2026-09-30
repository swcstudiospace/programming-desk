# C-4 · `loop_acks` is missing from the shared receipt contract

**Owner:** bot-06-quality-security · **File:** `skills/verification-receipts/SKILL.md`

## The defect

`skills/verification-receipts/SKILL.md` §2 is the receipt contract every seat reads. It documents
`approvals`, and says nothing about `loop_acks` — so the only description of a degraded-mode turn
ack lives in `skills/desk-bootstrap/desk-production-loop/SKILL.md` §3.1, which is LEAD's skill and
not where a seat looks up receipt structure.

The practical consequence is not documentation tidiness. A seat reading only the shared contract
sees one field for recorded approvals and puts its turn ack there, which is the exact G-6 hazard
§3.1 exists to prevent.

## Patch

In the §2 example receipt, beside `"approvals": []`:

```json
  "approvals": [],
  "loop_acks": [],
```

and after the example, a section that says why they are two fields:

> **`approvals` and `loop_acks` are two different things and must not be merged.**
>
> - **`approvals[]`** is G-5/G-6's surface: one entry per **destructive or deploy operation**, each
>   carrying `operation`, `approved_by`, `at` and `blast_radius`. `ci/gates/check_rollback.py`
>   validates every entry once any destructive command is present, and pairs entries to destructive
>   commands **by count**.
> - **`loop_acks[]`** records a **degraded-mode turn acknowledgement** — a human saying "work this
>   ticket even though the memory brief failed", per
>   `skills/desk-bootstrap/desk-production-loop/SKILL.md` §3. It authorises a *turn*, never an
>   operation.
>
> Putting a turn ack in `approvals[]` breaks G-6 in both directions: without `at`/`blast_radius` it
> fails a receipt whose destructive op was properly approved, and *with* them it silently satisfies
> the count for a destructive op nobody approved. That is why it has its own field, and why
> `check_rollback.py` must never be taught to read `loop_acks`.
>
> Each `loop_acks` entry:
>
> ```json
> { "condition": "brief_degraded",
>   "operation": "degraded-loop: repo work without a memory brief",
>   "ack_id": "ack-2026-09-30-004",
>   "human_granted_by": "Ove",
>   "relayed_by": "bot-00-programming-lead",
>   "at": "2026-09-30T09:41:11Z",
>   "scope": "one turn, ticket intake-ack-idempotent" }
> ```
>
> **`human_granted_by` is a person, and it is required.** The point of a degraded-mode ack is that
> somebody who knows what the brief could not tell the seat said go ahead, so a seat id there
> authorises nothing. A build seat asks LEAD and LEAD asks the human, which makes `relayed_by` the
> LEAD seat and `human_granted_by` the person at the end of that chain; LEAD's own degraded turns are
> acked by the human directly, with `relayed_by` null. G-2 fails an entry whose `human_granted_by` is
> absent or looks like a seat — an entry naming a bot is worse than a missing one, because it reads
> as compliance.

The field is **optional**: a receipt for a turn that never went degraded carries `[]` or omits it,
and that must stay a pass.

## How to tell it worked

Nothing to execute — it is prose. What makes it checkable is that the loop skill's `verify.sh`
asserts the shared contract mentions `loop_acks` and warns against `check_rollback.py` reading it;
that assertion is currently disabled with a pointer here, and lands when this does.

## Pairs with C-3

[C-3](./C-3-quality-loop-acks-g2.md) is the gate. Contract without gate is unenforced; gate without
contract is unanticipated. Land them together.
