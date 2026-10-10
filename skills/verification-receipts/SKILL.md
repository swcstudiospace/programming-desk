---
name: verification-receipts
description: Produce a verification receipt that passes gate G-2. Use before making any completion claim — this is the artefact that separates "I ran it" from "it looks right".
bots: [all]
gates: [G-2]
---

# Verification Receipts

## L1 — Summary

**A claim without a command behind it is not a claim. It is a guess with confident phrasing.**

The receipt records what you actually ran and what actually happened. Gate G-2 validates it, and
CI can re-run your commands — which is the point. You can be certain about code you never
executed; you cannot fabricate an exit code that survives re-execution.

**Decision tree:**

```
About to say "done", "works", "fixed", "tested", or "verified"?
│
├─ Did you run a command and see its exit code?
│   ├─ NO ──▶ You are not done. Run it. §1
│   └─ YES
│       │
│       Does the command actually prove the claim?
│       ├─ NO ──▶ Wrong evidence. §3 — a lint pass does not prove tests pass
│       └─ YES ──▶ Write the receipt. §2
│
└─ Could not verify some of it?
    └─▶ That is fine and normal. Put it in `unverified` with the reason. §4
        Honest incompleteness passes. Silent incompleteness does not.
```

**The one-line test:** if someone re-ran every command in your receipt right now, would the
claims still hold? If you are not sure, you have not verified them.

---

## L2 — Method

### §1 What counts as verification

| Claim | Insufficient | Sufficient |
|---|---|---|
| "The code compiles" | Reading it | `cargo build` → 0 |
| "Tests pass" | Tests exist | `pytest` → 0, with the output |
| "The bug is fixed" | The fix looks right | Reproduction fails before, passes after |
| "The UI renders" | The component type-checks | Rendered it and looked at it |
| "It's faster" | The algorithm is better | Benchmark, before and after, with numbers |
| "The migration is safe" | It reads fine | Applied AND reverted on representative data |
| "It works on Android 8" | It compiles at minSdk 26 | Ran on an API 26 device or emulator |
| "No secrets committed" | I didn't add any | Secret scanner → 0 |

The pattern: **the evidence has to be capable of failing.** Reading your own code cannot fail —
it confirms the code matches your intent, which was never in question. A test run can fail, which
is exactly why it is evidence.

### §2 Receipt structure

**Path:** `.receipts/<bot-id>/<task-id>.json` — your own directory. You own it; no other
bot may write there, which keeps one bot from editing another's evidence.

Git ignores `.receipts/**/*.json`; stage the real receipt with
`git add -f .receipts/<bot-id>/<task-id>.json`. G-2 recognizes only literal
leading `git add` force-staging of the authoring bot's receipt, with canonical
unquoted paths and any additional staged paths declared in `files_changed`.
An `&&` tail is checked normally; force-push, skipped hooks/tests, masked
failures and unsupported shell forms are not exempt. Record the actual
command unchanged. Force-staging never supplies the independent `approved_by`.

```json
{
  "task_id": "fix-pagination-offset",
  "bot": "bot-02-web-edge",
  "started_at": "2026-09-17T09:14:00Z",
  "completed_at": "2026-09-17T09:41:00Z",
  "commands": [
    { "cmd": "deno test web/pagination_test.ts", "exit_code": 1, "duration_s": 3.1,
      "output_tail": "FAILED page 2 with exactly 20 items returns empty" },
    { "cmd": "deno test web/pagination_test.ts", "exit_code": 0, "duration_s": 3.0,
      "output_tail": "ok | 14 passed | 0 failed" },
    { "cmd": "deno check web/**/*.ts", "exit_code": 0, "duration_s": 5.4 },
    { "cmd": "deno lint web/", "exit_code": 0, "duration_s": 1.2 }
  ],
  "claims": [
    { "claim": "Reproduced the reported bug", "evidence_command_index": 0,
      "expects_failure": true },
    { "claim": "Fix resolves it; all pagination tests pass", "evidence_command_index": 1 },
    { "claim": "Type-check passes", "evidence_command_index": 2 }
  ],
  "unverified": [
    "Not checked against a live dataset — local fixtures only",
    "Safari not tested; no browser available in this environment"
  ],
  "files_changed": ["web/lib/pagination.ts", "web/pagination_test.ts"],
  "contract_changes": [],
  "rollback_plan": null,
  "approvals": [],
  "loop_acks": [],
  "approved_by": "bot-06-quality-security"
}
```

**`approvals` and `loop_acks` are two different things and must not be merged.**

- **`approvals[]`** is G-5/G-6's surface: one entry per **destructive or deploy operation**, each
  carrying `operation`, `approved_by`, `at` and `blast_radius`. `ci/gates/check_rollback.py`
  validates every entry once any destructive command is present, and pairs entries to destructive
  commands **by count**.
- **`loop_acks[]`** records a **degraded-mode turn acknowledgement** — a human saying "work this
  ticket even though the memory brief failed". It authorises a *turn*, never an operation. There
  is no separate loop-skill document to consult: the two conditions it can carry
  (`brief_degraded`, `brief_no_revision_marker`) and every required field are defined here and
  enforced by `ci/gates/check_receipt.py`'s `LOOP_ACK_CONDITIONS` — this file is the contract.

Putting a turn ack in `approvals[]` breaks G-6 in both directions: without `at`/`blast_radius` it
fails a receipt whose destructive op was properly approved, and *with* them it silently satisfies
the count for a destructive op nobody approved. That is why it has its own field, and why
`check_rollback.py` must never be taught to read `loop_acks`.

Each `loop_acks` entry:

```json
{ "condition": "brief_degraded",
  "operation": "degraded-loop: repo work without a memory brief",
  "ack_id": "ack-2026-09-30-004",
  "human_granted_by": "Ove",
  "relayed_by": "bot-00-programming-lead",
  "at": "2026-09-30T09:41:11Z",
  "scope": "one turn, ticket intake-ack-idempotent" }
```

**`human_granted_by` is a person, and it is required.** The point of a degraded-mode ack is that
somebody who knows what the brief could not tell the seat said go ahead, so a seat id there
authorises nothing. A build seat asks LEAD and LEAD asks the human, which makes `relayed_by` the
LEAD seat and `human_granted_by` the person at the end of that chain; LEAD's own degraded turns are
acked by the human directly, with `relayed_by` null. G-2 fails an entry whose `human_granted_by` is
absent, non-string, or looks like a seat (including a `desk-<seat>` connector name) — an entry
naming a bot is worse than a missing one, because it reads as compliance. A JSON `true` or a bare
id is not a name: `human_granted_by` must be a string.

**`scope` binds the ack to this turn, not to the desk in general.** G-2 checks that `scope`
contains the receipt's own `task_id`, so an ack copied from an earlier ticket, or a blanket phrase
like "all turns", does not silently authorise a turn it was never written for.

The field is **optional**: a receipt for a turn that never went degraded omits it or carries `[]`.
Setting it to `null` is neither — `loop_acks` must be a list whenever the key is present, so an
explicit null fails rather than being read as "no field at all".

Note command index 0: **a failing command is valuable evidence.** It proves the bug was real
before the fix. A receipt that only ever shows green is often a receipt where the reproduction
step was skipped.

A claim citing a failing command sets `"expects_failure": true`. The gate then requires that
command to have a **non-zero** exit — so the flag cannot be used to excuse a claim whose evidence
actually failed. It asserts "this was supposed to fail", not "ignore the exit code".

Under `--strict`, an `expects_failure` claim worded exhaustively ("every value is still empty") can
pass — a search that exits non-zero exactly when it finds nothing across its whole target is
reproduction evidence and total coverage at once — but only when its cited command is the receipt's
only command, evidence-wise. The moment the receipt records anything else (the fix that follows a
reproduction, say), that claim is rejected: other commands elsewhere cannot make THIS claim any more
exhaustive, so their presence is only ever a sign of the original bypass this check exists to catch —
a narrow, failing command padded by an unrelated one recorded for something else. With nothing else
in the receipt to borrow from, the cited command's own scope is this claim's entire evidence, left to
a human reviewer (`approved_by`) to judge, the same as any other evidence-matching question.

**One specific shape of "something else" is not padding: a quiet-search sibling existence check.**
`test -f X && grep -q PATTERN X` (or `--quiet`) prints nothing whether it matches or finds nothing —
that silence is indistinguishable from `test -f X` failing and the chain short-circuiting before
grep ever runs, so on its own this compound cannot back an exhaustive claim at all. To use one, add a
**second command, recorded earlier in `commands`,** that tests the exact same path with a flag whose
predicate **implies** the compound's own gate flag, and itself exits 0 — a bare `test -f X`/`-e`/`-d`/
`-r`, or the `[ ... ]` equivalent, nothing chained after it. That sibling is the one command this gate
does not count as padding, because it is the only thing that can prove X would have passed the gate's
own check when the quiet search ran. "Implies" is a one-way relationship, not flag equality: `-f`
(regular file), `-d` (directory) and `-r` (readable) each require the target to exist as a
precondition of their own stricter test, so any of them passing on X also proves a weaker `-e` gate on
X would pass — a `test -f config.yaml` sibling DOES corroborate a compound gated on `test -e
config.yaml`. It does not run the other way: `-e` implies only itself, and `-f`/`-d`/`-r` do not imply
each other (a directory existing says nothing about whether `test -f` on that same path would also
succeed — it wouldn't), so an `-e` sibling must not corroborate an `-f`-gated compound, and `test -d
config` next to a compound gated on `test -f config` still proves nothing. Get any part wrong and the
gate still rejects it: a sibling recorded AFTER the quiet search only proves X exists *now*, not that
it did when the search ran (it could have been created in between); a sibling naming a different path
— even one that merely contains the target as a substring, like `config.yaml.bak` next to
`config.yaml` — proves nothing about the target at all. Equivalent relative spellings of the *same*
path do still match — `test -f ./config.yaml` corroborates a compound gated on `config.yaml` — since
path tokens are normalized (leading `./`, doubled separators) before comparison. A **trailing slash**
is normalized away only for `-d`: `test -d config` and `test -d config/` are the same check, because a
directory check's own predicate already requires the target to resolve as a directory, so the slash
can never change the answer. Every other flag keeps the slash significant: POSIX `test`/`[` requires a
trailing-slash path to resolve to a directory, so `test -f config.yaml/` fails for a regular file no
matter whether it exists, and a bare `test -f config.yaml` sibling must not be read as corroborating
that different, stricter gate. A `test -n X` sibling doesn't count either: `-n` tests whether a
*string* is non-empty, not whether a file exists, so it says nothing about the filesystem no matter
what its operand is.

Being the receipt's only command (or paired only with that one preceding sibling) is necessary but
not sufficient: the gate also rejects the two shapes of thin evidence that pattern most often. A
failure that reads back as the target being missing ("no such file or directory", "not found", ...) —
in `output_tail`, or in the command's own text outside any quoted argument — is not the same fact as
"the target was searched and found empty"; "file missing" must never stand in for "every value
empty". A quoted argument is exempted from that command-text check because it is what the command
searches *for*, not a report of what happened: `grep -c "not found" build.log` exiting 1 means the
phrase is nowhere in the file, which is exhaustive negative evidence, not a missing-target error. And
a command that *only* tests whether a path exists (`test -f X`, `[ -e X ]`, `stat X`, a bare `ls X`,
and nothing chained after it) never inspects content either way, so it cannot back a claim about what
that content is — but a real content search chained onto one, like `test -f X && grep ... X`, is
judged on the whole command, not just its existence-checking prefix. Neither check can verify that
the command's scope truly covers "every"/"all" — that judgment call still belongs to `approved_by`.

### §3 Matching evidence to claims

The most common G-2 failure is a claim citing a command that does not prove it.

| Claim | Cited | Problem |
|---|---|---|
| "Tests pass" | `ruff check` | Lint is not tests |
| "It builds" | `tsc --noEmit` | Type-checking is not building |
| "Works on device" | `assembleDebug` | Building is not running |
| "Migration is safe" | `pytest tests/unit` | Unit tests do not exercise a migration |
| "No regressions" | `pytest tests/test_new.py` | One new test file is not the suite |
| "Performance improved" | `cargo test` | Tests passing says nothing about speed |

Ask of every claim: **could this command have failed if the claim were false?** If not, it is the
wrong evidence.

### §4 `unverified` — the honest field

Mandatory. An empty array asserts you verified everything, which is rarely true and is checkable
against the change.

**Good entries** name what and why:

```
"iOS 15 not tested — only iOS 17 simulator available here"
"Behaviour under concurrent writes not verified — no load test in this environment"
"Production data volumes not simulated; tested against 1k rows, production is ~40M"
"Rollback exercised in staging, not production"
```

**Bad entries** are vague enough to be meaningless:

```
"Some edge cases"           ← which ones?
"Full testing"              ← what does that mean?
"Minor things"              ← minor to whom?
```

A specific `unverified` list is the most useful thing in the receipt for whoever reviews it. It
tells them exactly where to look, and it is the difference between a reviewer trusting your work
and a reviewer re-checking all of it.

### §5 Forbidden commands

These produce a green result from work that never ran. G-2 rejects them outright:

```
git commit --no-verify          pytest ... || true
./gradlew -x test               npm test --passWithNoTests   (on a suite that should have tests)
xcodebuild -skipTesting         terraform apply -auto-approve  (without recorded approval)
--skip-checks                   2>/dev/null                   (hiding an error stream)
```

If a check genuinely does not apply, say so in `unverified`. Do not silence it.

### §6 Self-approval

`approved_by` is never your own bot id. Reviews go to Bot 6 or a human.

A bot approving its own work is the same failure as the reviewer fixing the code: the independent
check disappears and nobody notices, because the paperwork still looks complete.

---

## Worked example — a bug fix done properly

```
1. REPRODUCE   deno test pagination_test.ts   → exit 1   ← the bug is real
2. INVESTIGATE read the code, find the off-by-one
3. FIX         change the offset calculation
4. RE-RUN      deno test pagination_test.ts   → exit 0   ← the fix works
5. REGRESS     deno test web/                 → exit 0   ← nothing else broke
6. CHECK       deno check && deno lint        → exit 0
7. RECEIPT     claims cite indices 0, 1, 3; unverified lists Safari and live data
```

Step 1 is the one most often skipped, and skipping it means step 4 proves nothing — you cannot
demonstrate you fixed a failure you never observed. The fix might be addressing a bug that was
never there while the real one persists.

---

## Failure modes

| Mode | Symptom | Fix |
|---|---|---|
| Claim without evidence | "Should work", "looks correct" | Run something that could fail |
| Mismatched evidence | Lint cited for a test claim | §3 — could this command have failed? |
| Empty `unverified` | Mobile change, no OS caveats | Almost always dishonest. Name what you skipped |
| Vague `unverified` | "some edge cases" | Name them specifically |
| No reproduction | Fix claimed, bug never observed failing | Reproduce first, always |
| Bypass command | `-x test`, `|| true` | §5 — rejected outright |
| Self-approval | `approved_by` is you | Route to Bot 6 |
| Summary exceeds receipt | "Fully working" on one unit test | Language matches evidence |
