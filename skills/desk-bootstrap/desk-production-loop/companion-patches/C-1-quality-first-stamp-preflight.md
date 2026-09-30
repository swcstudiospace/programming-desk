# C-1 · No first stamp can succeed: the preflight gates the pre-stamp receipt

**Owner:** bot-01-systems-backend · **File:** `services/desk-gateway/src/desk_gateway/tools/quality.py`

## The defect

`receipt_approve` runs the gates over the receipt **as fetched**, then stamps:

```python
check = await repo.receipt_check(receipt, receipt.get("bot") or "", False, args["receipt_path"])
if not check.get("ok"):
    return failure("gate_failed", "the receipt does not pass G-2/G-3/G-5/G-6 before stamping", ...)
receipt["approved_by"] = ctx.bot_id          # ← unreachable on a first stamp
```

`repo.receipt_check` writes the receipt it is given to a scratch file and runs `check_receipt.py`
over it, and that gate fails an absent `approved_by` **unconditionally** — the check is not behind
`--strict`, and this preflight passes `strict=False` anyway:

```python
# ci/gates/check_receipt.py
approved_by = receipt.get("approved_by")
if not approved_by:
    problems.append("'approved_by' is missing — work must be reviewed by someone else")
```

An unstamped receipt is the **expected input** to this tool. So the one state it exists to change is
the one state it refuses, and every correct first stamp returns `gate_failed` forever.

## Reproduction (no gateway needed)

```sh
R=.receipts/bot-00-programming-lead/lead-production-loop-spe-4794.json
# what the preflight sees today:
python3 ci/gates/check_receipt.py --receipt "$R" --bot bot-00-programming-lead
#   G-2 FAIL — 'approved_by' is missing        exit 1

# the same receipt with the stamp applied:
python3 - <<'EOF'
import json
d = json.load(open(".receipts/bot-00-programming-lead/lead-production-loop-spe-4794.json"))
d["approved_by"] = "bot-06-quality-security"
d["approved_at"] = "2026-09-30T16:00:00Z"
json.dump(d, open("/tmp/candidate.json", "w"), indent=2)
EOF
python3 ci/gates/check_receipt.py --receipt /tmp/candidate.json --bot bot-00-programming-lead
#   G-2 PASS                                    exit 0
rm -f /tmp/candidate.json
```

The deadlock is the only thing between that receipt and a passing preflight.

## Patch

Permit the expected-absent `approved_by`, set it, then gate what will actually be committed — build
a candidate and run the gates over the candidate:

```python
candidate = dict(receipt)
candidate["approved_by"] = ctx.bot_id
candidate["approved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
if args.get("note"):
    candidate["approval_note"] = redact_text(args["note"])
check = await repo.receipt_check(candidate, candidate.get("bot") or "", False, args["receipt_path"])
if not check.get("ok"):
    return failure("gate_failed", "the receipt does not pass G-2/G-3/G-5/G-6 once stamped",
                   gates=check.get("gates"))
receipt = candidate
```

This is better than the old order independently of the deadlock: the gates now run over exactly the
bytes that get committed, rather than over a pre-stamp state that is never what lands.

The alternative — a `--pre-approval` flag on `check_receipt.py` that exempts the `approved_by`
check — would also clear the deadlock but leaves the gates validating a state that never reaches the
branch, so it is the worse of the two.

## How to tell it worked

The reproduction above, run against the tool rather than the gate: `desk_receipt_approve` on an
unstamped receipt returns `ok` instead of `gate_failed`, and the commit it pushes carries
`approved_by`.

## Take C-2 first

[C-2](./C-2-systems-approve-toctou.md) is in this same function and loses committed work. Landing
C-1 alone makes first stamps start succeeding, which widens the window in which C-2's blind
overwrite can fire. Both together, or C-2 first.
