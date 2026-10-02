# Quality Gates

Each gate maps an obligation to the **script that enforces it** and the **evidence it produces**.
Gates are executable. A gate that exists only as a rule in a prompt is a suggestion.

Run them all locally:

```bash
python3 ci/gates/run_all.py --base origin/main --receipt .receipts/<bot-id>/<task-id>.json
```

## Scope of this document

G-1…G-6 are **this repository's** gates. They are Python scripts under `ci/gates/`, versioned
with the change they judge, and they run against a diff and a receipt.

**Greptile is not one of them.** It is an external code-review service in the `swcstudio` org,
driven over MCP after a draft PR opens. It reviews the pull request; it never executes these
scripts and cannot satisfy them. A green Greptile review is not a green gate run, and a green
gate run is not a Greptile review.

Both are required before a merge claim. The rules for keeping them apart are in
[Greptile is not a gate](#greptile-is-not-a-gate) at the end of this file.

---

## G-1 — Path ownership

**Rule.** A bot may only modify paths it owns in `ownership.yaml`. No path may be unowned.

**Why.** This is the control that makes a platform/domain decomposition survive contact with a
real feature. Without it, "add push notifications" puts Bot 1, 3, 4 and 5 on the same branch with
no authority, and the merge resolves by timing rather than decision.

Unowned paths fail too, and that is deliberate. A file matching no pattern is exactly where two
bots collide without either noticing — treating it as a default-allow hides the collision until
it produces a conflict nobody can adjudicate.

**Enforced by.** `ci/gates/check_ownership.py`

```bash
python3 ci/gates/check_ownership.py --bot bot-03-android --base origin/main
python3 ci/gates/check_ownership.py --validate-manifest   # manifest self-check
```

**Evidence.** The diff's file list, each resolved to an owner, in the CI log.

**Escape hatch.** None by design. Cross-bot work uses `docs/cross-bot-protocol.md`.

---

## G-2 — Verification receipts

**Rule.** No completion claim without a receipt recording commands actually run and their actual
exit codes. Every claim cites a command. `unverified` must be present and honest.

**Why.** This is the gate the whole system exists for. A coding agent's characteristic failure is
not writing bad code — it is writing plausible code, reasoning convincingly about why it works,
and reporting success without ever executing it. Every downstream quality problem traces back to
a completion claim that was never grounded in an observation.

The gate deliberately does not ask the bot whether it verified something. It asks for the exit
code, and CI can re-run the command. A model can be confident about a claim it never tested; it
cannot fabricate a `0` that survives re-execution.

**Enforced by.** `ci/gates/check_receipt.py`

```bash
python3 ci/gates/check_receipt.py --receipt .receipts/bot-03-android/feat-push.json --bot bot-03-android
```

**Checks:**

| Check | Failure mode it catches |
|---|---|
| Receipt exists for the task | Silent completion claim |
| At least one command with a recorded exit code | "I reviewed it and it looks right" |
| Every claim cites a valid command index | Claims floating free of evidence |
| Cited commands exited 0 | Claiming success on a failing command |
| `unverified` present | Silent partial verification |
| `approved_by` ≠ the authoring bot | Self-approval |
| No command matches the forbidden list | `--no-verify`, `-DskipTests`, `|| true` |

That last one is worth naming: `git commit --no-verify`, `./gradlew -x test`, `pytest || true` and
friends produce a green receipt from a build that never ran. They are rejected outright.

**Evidence.** The receipt JSON, retained with the commit.

---

## G-3 — No committed secrets

**Rule.** No credential, token, private key or connection string in committed code.

**Why.** A secret in git history is a secret that has been disclosed, even after the commit is
reverted. Detection at commit time is the only cheap moment.

**Enforced by.** `ci/gates/check_secrets.py` — runs in CI and in the pre-commit hook.

**Detects.** AWS keys, GitHub/GitLab tokens, Slack tokens, Stripe keys, Google API keys, private
key blocks, JWTs, connection strings with inline credentials, and high-entropy strings assigned to
suspiciously named variables.

**False positives.** Mark the line `# pragma: allowlist secret` with a comment explaining why.
The allowlist entry is reviewable; a disabled scanner is not.

**On a real hit.** The secret is already compromised. Rotate it first, then remove it from
history. Removing it from the working tree is not remediation.

---

## G-4 — Contract-first changes

**Rule.** A breaking change to a contract surface requires a version bump, a migration note, and
an acknowledgement from every consumer in `contract_consumers`. Any change, breaking or not,
requires a change document whose declared surfaces (`surface`, plus an optional `surfaces` list)
cover every contract-surface file in the diff, other than the change document itself and the
rest of `contracts/changes/`.

That coverage requirement is what binds a document to a change. Callers select the document by
globbing `contracts/changes/`, so without it a document left behind after its own change merged
can be picked up and validate a later one — and a breaking change with no acknowledgements
passes on the strength of a stale non-breaking record. Archive a merged document; the gate
refuses it either way.

**Why.** In a platform decomposition, contracts are the only shared surface. A field rename that
looks trivial in the API repo breaks the iOS client silently, and the break is discovered weeks
later by a user. Consumer acknowledgement moves that discovery to the pull request.

**Enforced by.** `ci/gates/check_contracts.py`

**Breaking, by definition:**

- Removing or renaming a field, endpoint, event or method
- Narrowing a type, or making an optional field required
- Changing a field's semantics without changing its name — the most dangerous kind, because no
  tool detects it. Declare it explicitly.
- Removing an enum value
- Tightening validation on an existing input

**Non-breaking:** adding an optional field, adding an endpoint, adding an enum value where
consumers handle unknowns, widening a type.

**Evidence.** The contract diff, the version bump, the migration note, the acknowledgement list.

---

## G-5 — Rollback plans

**Rule.** No deployment without a rollback plan, stated in the receipt, that has been exercised.

**Why.** "Roll back" is not a plan. A plan names the command, the expected time to recover, and
what happens to data written under the new version. Migrations in particular are often
irreversible in practice — discovering that during an incident is expensive.

**Enforced by.** `ci/gates/check_rollback.py`

**A plan states:** the command or procedure, expected recovery time, data implications, whether
it was exercised in staging, and what makes it not applicable if it isn't.

---

## G-6 — Destructive operations

**Rule.** Destructive operations need explicit human approval recorded in the receipt before
execution.

**Destructive:**

| Category | Examples |
|---|---|
| Data | `DROP`, `TRUNCATE`, destructive migrations, bulk deletes |
| Infra | `terraform destroy`, removing stateful resources, deleting a cluster or namespace |
| Git | Force-push to a shared branch, history rewrite, tag deletion |
| Release | Unstaged rollout to production, removing a published version |
| Access | Rotating shared credentials, altering IAM, revoking certificates |

**Enforced by.** `ci/gates/check_rollback.py`, checking `approvals[]` in the receipt.

**Approval records** who approved, when, what exactly was approved, and the blast radius as
understood at approval time. A blanket "yes go ahead" on a Slack thread is not an approval record.

---

## Gate test schedule

| Gate | Test | Frequency |
|---|---|---|
| G-1 | Edit an unowned path; expect fail. Edit another bot's path; expect fail | Each release |
| G-2 | Claim without a receipt; claim citing a failing command; self-approval — all expect fail | Each release |
| G-3 | Commit a known test credential; expect fail | Each release + on hook change |
| G-4 | Remove a contract field without acks; expect fail | Each release |
| G-5 | Deploy receipt with no rollback plan; expect fail | Each release |
| G-6 | Destructive command with no approval; expect fail | Each release |

`ci/tests/test_gates.py` implements all of these against real fixture repositories, so the tests
exercise the gates the way CI does rather than mocking them.

---

## Greptile is not a gate

Operators keep asking which review is *the* required one before merge. Both are. They check
different things, run in different places, and fail for different reasons. Confusing them
produces the two failures this section exists to stop: merging on a green gate run that no
human or reviewer ever looked at, and treating a Greptile pass as though it cleared G-1…G-6.

### Side by side

| | **G-1…G-6** | **Greptile** |
|---|---|---|
| What it is | Six executable checks owned by this repo | External code-review service (`swcstudio` org) |
| Lives in | `ci/gates/*.py`, versioned with the change | SaaS, reached over MCP `user-greptile` |
| Runs | Local pre-flight, `ci/hooks/pre-commit` (G-3 only), and wherever CI invokes `run_all.py` | After a **draft PR is open**, against one PR head commit |
| Triggered by | `python3 ci/gates/run_all.py --bot … --base … --receipt …` | `trigger_code_review` with the repo tuple + `prNumber` |
| Answers | Did this bot stay in its lane, produce evidence, leak a secret, break a contract, plan a rollback, get approval for a destructive op? | Is this code wrong? Logic, edge cases, line comments |
| Verdict shape | Per-gate exit code. Deterministic and re-runnable on any checkout | `COMPLETED` / `FAILED` / `SKIPPED`, plus comments carrying an `addressed` flag |
| Who records it | Any seat runs them; QUALITY (bot-06) records the result in the merge claim | QUALITY records the verdict; LEAD may fire the trigger |
| Waivable | **No.** See [Waivers](#waivers) | Only on explicit instruction from Ove, with a waiver receipt |
| Governed by | This file, `skills/verification-receipts` | `skills/greptile-merge-gate`, `docs/github-sot-orchestration.md` §4 |

No GitHub Actions workflow is committed in this repo, so "CI" here means whatever runtime
invokes `run_all.py` — today that is the implementing seat's pre-flight plus QUALITY's re-run.
The gates do not fire on a push by themselves. Run them yourself before you push.

### Order of operations

```
local edit
    → seat pre-flight: G-1, G-3, G-4, G-5/G-6 green; G-2 green except approved_by
    → commit  (pre-commit hook re-runs G-3 only)
    → push → draft PR opened
    → Greptile trigger on the PR head        [only possible once a PR exists]
    → poll to terminal status
    → address comments in code, or waive on Ove's instruction
    → independent review stamps approved_by, then re-runs run_all.py
         QUALITY (bot-06) for a build seat's work
         LEAD (bot-00) or a human for QUALITY's own work — bot-06 never stamps itself
         a human, and only a human, for a change to the gates themselves
    → full G-1…G-6 green, recorded with the Greptile status in the merge-claim receipt
    → merge (human, protected branch)
```

**A seat cannot get a fully green `run_all.py` before it pushes, and should not try.** G-2
requires `approved_by`, and rejects a bot that approves its own work
(`ci/gates/check_receipt.py`). That field stays empty until QUALITY reviews the build, so G-2
is expected to fail on the authoring seat's own pre-flight with exactly one problem:
`'approved_by' is missing`. Run the other gates individually before pushing:

```bash
python3 ci/gates/check_ownership.py --bot <bot-id> --files <changed paths>
python3 ci/gates/check_secrets.py   --files <changed paths>
python3 ci/gates/check_contracts.py --base origin/main         # add --change <doc> for contract work
python3 ci/gates/check_rollback.py  --receipt .receipts/<bot-id>/<task-id>.json
python3 ci/gates/check_receipt.py   --receipt .receipts/<bot-id>/<task-id>.json --bot <bot-id>
```

**G-4 needs `--change` as soon as the diff touches a contract surface.** Without it,
`check_contracts.py` fails with *"contract surfaces changed but no change document supplied"* —
it does not matter that the seat has written a valid change document, only that the gate was
pointed at it. The bare form above is correct only for a diff that touches no contract surface:

```bash
python3 ci/gates/check_contracts.py --base origin/main --change contracts/changes/<change-id>.yaml
```

The change document declares `change_id`, `proposed_by`, `surface`, `breaking`, `version`,
`summary` and `semantic_changes`, plus consumer acknowledgements. `semantic_changes` is
mandatory **even when empty** — set it to `[]` to confirm there are none. Omitting it fails G-4
with `missing 'semantic_changes'`, on non-breaking changes too, because no tool can detect a
field whose meaning changed while its name and type did not. See `docs/cross-bot-protocol.md`
and `skills/contract-first-changes`.

The last command is expected to fail on `approved_by` alone. Any *other* G-2 problem is the
seat's to fix before pushing. `run_all.py` is the full run, and it first comes back green after
the independent stamp — not before the commit.

**When QUALITY is the author, QUALITY is not the approver.** G-2 rejects `approved_by` equal to
the authoring bot, so bot-06 cannot stamp a change to its own files — including this document.
The stamp then comes from LEAD (`bot-00-programming-lead`) or from a human, recorded as
`human:<name>`; both forms are already in use under `.receipts/bot-06-quality-security/`.
`skills/verification-receipts` puts it generally: `approved_by` is never your own bot id.
Until that independent stamp lands, the receipt's `approved_by` stays **absent**, not
self-filled, and G-2 fails closed — which is the correct state for a QUALITY-authored change
awaiting review, not a defect to engineer around.

**A change to the gates themselves needs a human, and LEAD's stamp will not do.** For edits
under `ci/gates/**` and `ci/hooks/**`, `approved_by` must be a person: *"You never approve your
own gate change. A human does"* (`prompts/QUALITY.xml`), echoed by the QUALITY checklist in
`skills/greptile-merge-gate`. **G-2 cannot enforce this**, and that is the point of stating it
here: `check_receipt.py` only compares the approver against the authoring bot, so a LEAD stamp
on a gate change passes the gate while breaking the rule. The gate that guards the gates is the
one place the evidence has to come from outside the system, so the reviewer who accepts a gate
change is accepting it on the record, not on a green check. This is a policy constraint the
receipt carries; it is not something the tooling will catch for you.

Greptile is not part of dispatch and not part of implementation. It cannot run before the draft
PR exists, which is why a seat finishing its work has satisfied at most half of what a merge
claim needs.

A successful trigger means the review was **queued**, not that analysis finished. Poll until the
status is terminal.

### The merge claim needs both

| G-1…G-6 | Greptile | Merge claim |
|---|---|---|
| all pass | `COMPLETED`, no unaddressed comments | Allowed |
| all pass | `COMPLETED`, comments with `addressed=false` | **Blocked** until each is fixed in code or waived |
| all pass | `FAILED`, `SKIPPED`, or unavailable | **Blocked.** Record `unverified`; LEAD escalates. `SKIPPED` is not a pass |
| any fail | any status | **Blocked.** A clean review never clears a failed gate |
| not run | any status | **Blocked.** No completion claim without a receipt (G-2) |

A Greptile review covers only the commit it ran on. If the branch moves, the verdict does not
move with it: re-trigger on the new tip. `merge_claim.allowed` stays false, and `approved_by`
stays empty, until Greptile is `COMPLETED` on the tip being merged — the merge-claim head rule
in `docs/desk-operating-model.md`.

### Waivers

**G-1…G-6 have no waiver.** A failing gate is fixed, not argued with. The one annotation that
looks like an exception is not one: a `# pragma: allowlist secret` line on a G-3 false positive
is a reviewable statement inside the diff, and the gate still runs and still passes on its own
terms.

G-2 helps here, but only as far as it actually reaches: it matches each command string recorded
in the receipt against a fixed bypass list — `--no-verify`, `-x test`, `--skip-tests`,
`-DskipTests`, `|| true`, `--dry-run` and the rest in `BYPASS_PATTERNS`
(`ci/gates/check_receipt.py`) — and rejects the receipt on a hit. That catches the bypass forms
on the list *when the command is in the receipt*. It does not, and cannot, tell you that a
scanner was enabled or that a suite really ran: a command left out of the receipt is invisible to
it, and an unlisted way to disable a check passes. A green G-2 is evidence about the commands
recorded, not proof that the right commands were run (PD-3).

**A Greptile comment may be waived only on an explicit instruction from Ove.** QUALITY does not
waive on its own judgement, and neither does LEAD or the implementing seat. QUALITY's role is to
record the waiver, acknowledge it, and keep the scope honest — not to author it. "Cosmetic",
"pre-existing", "out of scope" and "the author disagrees" are arguments to put to Ove, not
grounds to waive.

A waiver receipt (under `.receipts/<bot-id>/`, or a PR comment linked from the receipt) records:

| Field | Content |
|---|---|
| Instruction | That Ove instructed the waiver, when, and where it was given |
| Comment ids | Every Greptile comment id the waiver covers — never "all open comments" |
| Why | The reasoning as stated, not a paraphrase that widens it |
| QUALITY ack | That bot-06 acknowledged and recorded it |
| Scope | What the waiver does **not** cover, so a later defect cannot shelter under it |
| Head | The commit the waived review ran on; a waiver does not follow the branch |

Not a waiver, in any combination: silence on a comment, flipping `addressed=true` with no code
change, "we'll fix it in a follow-up PR" with no commit, re-triggering until a run comes back
`SKIPPED`, or a green G-1…G-6 run. Waiving is reviewable. Ignoring Greptile is not.

Receipts under `.receipts/bot-06-quality-security/` written before this rule was recorded show
QUALITY-authored waivers without an Ove instruction field. They are history, not precedent.

> **Known divergence.** `docs/github-sot-orchestration.md` §4.2 still describes a waiver in terms
> of who waived, the comment ids, why, and QUALITY's acknowledgement — without the
> explicit-instruction condition above. That file is owned by `bot-00-programming-lead`; this one
> is owned by `bot-06-quality-security`, and G-1 stops either seat from editing the other's file.
> **This section is the operative rule until LEAD reconciles §4.2.** A waiver authored against
> §4.2 alone, with no instruction from Ove, does not clear a merge claim.

### Quick answers

| Operator question | Answer |
|---|---|
| "The gates are green — can I merge?" | No. That is G-1…G-6. Greptile runs separately, on the PR |
| "Greptile approved — do I still need the gates?" | Yes. Greptile does not check ownership, receipts, secrets, contracts, rollback or destructive-op approval |
| "Greptile is down / `get_me` says needsAuth." | Blocked. Record `unverified` and escalate to LEAD. Never write "Greptile clean" |
| "Greptile came back `SKIPPED`." | Not a pass. Re-trigger on the tip; if it stays non-`COMPLETED`, escalate |
| "It's a trivial nit — can I waive it?" | Only with an explicit instruction from Ove, recorded in a waiver receipt |
| "Do the gates run automatically on my branch?" | Only G-3, via `ci/hooks/install.sh`. Run `run_all.py` yourself before pushing |
| "I pushed a fixup after the review passed." | The verdict does not cover the new tip. Re-trigger |
| "Can I run Greptile before opening the PR?" | No. It reviews a pull request; there is nothing to review yet |

### Where the rest of the rules live

| Concern | File |
|---|---|
| Greptile trigger, polling, and the QUALITY checklist | `skills/greptile-merge-gate/SKILL.md` |
| Receipt shape, claims, `unverified` (the G-2 artefact) | `skills/verification-receipts/SKILL.md` |
| Greptile gate policy and the PR status pipeline | `docs/github-sot-orchestration.md` §3.4, §4 |
| Merge-claim head rule (review must cover the tip) | `docs/desk-operating-model.md` |
| Greptile auth failure handling during intake | `docs/intake-e2e-runbook.md` |
| Path → owner for every gate and skill file | `ownership.yaml` |
