# Quality Gates

Each gate maps an obligation to the **script that enforces it** and the **evidence it produces**.
Gates are executable. A gate that exists only as a rule in a prompt is a suggestion.

Run them all locally:

```bash
python3 ci/gates/run_all.py --base origin/main --receipt .receipts/<bot-id>/<task-id>.json
```

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
cover every contract-surface file in the diff.

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
