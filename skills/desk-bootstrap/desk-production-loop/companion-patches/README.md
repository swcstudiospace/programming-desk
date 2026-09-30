# Companion patches this loop needs, and who owns them

Four changes the desk production loop depends on and **LEAD cannot make**. Each is specified here —
the defect, how to reproduce it, the patch, and how the owner can tell it worked — so the owning seat
gets a specification rather than a diff somebody else wrote.

Round 9 of this PR's review did land these as code under bot-00 attribution. That was withdrawn in
round 10: a LEAD PR cannot carry QUALITY's or SYSTEMS' files, G-1 rejects them, and asking reviewers
to wave a red G-1 through is worse than waiting. Reverted to `origin/main`, byte-identical, in
commit `45ed680`.

| # | File | Owner | What |
|---|---|---|---|
| [C-1](./C-1-quality-first-stamp-preflight.md) | `services/desk-gateway/.../tools/quality.py` | bot-01-systems-backend | Preflight gates the pre-stamp receipt, so no first stamp can ever succeed |
| [C-2](./C-2-systems-approve-toctou.md) | `services/desk-gateway/.../tools/quality.py` | bot-01-systems-backend | `receipt_approve` reads at one sha and commits at another — it can silently overwrite a newer receipt |
| [C-3](./C-3-quality-loop-acks-g2.md) | `ci/gates/check_receipt.py` | bot-06-quality-security | `loop_acks` has no gate: a seat can name itself as the human who granted a degraded-mode ack |
| [C-4](./C-4-quality-receipt-contract.md) | `skills/verification-receipts/SKILL.md` | bot-06-quality-security | The shared receipt contract does not mention `loop_acks`, so only this skill describes it |

C-1 and C-2 are both in `receipt_approve` and touch adjacent lines; taking them together is easier
than either alone, and C-2 is the one that matters more. **C-1 without C-2 is worse than neither** —
it makes the stamping path work while leaving it able to clobber a concurrent update.

## What is true on the desk until these land

Stated plainly so nothing in this skill reads as a claim about tools that work:

- **A first QUALITY stamp cannot be obtained.** `approved_by` on
  `.receipts/bot-00-programming-lead/lead-production-loop-spe-4794.json` is empty and G-2 fails
  closed on it. That is the accurate state, not an outstanding LEAD action.
- **`loop_acks` is checked by review only.** The shape in the loop skill's §3.1 is the contract; no
  gate enforces it, so a malformed or seat-granted entry passes CI today.
- **Neither of those is worked around.** No placeholder goes in `approved_by`, and no turn ack goes
  in `approvals[]` to borrow G-6's validation.

## Even with all four, the approval still moves the tip

C-1 and C-2 make `receipt_approve` correct. They do **not** make a receipt-file stamp the right
mechanism, because the tool commits the stamped receipt to the PR branch and that advances the head
past the sha the reviewer read — the tip chase in the loop skill's §4.1. The sha-bound, commit-free
approval described there (a check run on the reviewed sha; `approval_ref` in the receipt; G-2
resolving it against the current head) is a separate, larger change and is tracked in the receipt's
`blockers`, not here. These four are the floor, not the finish.
