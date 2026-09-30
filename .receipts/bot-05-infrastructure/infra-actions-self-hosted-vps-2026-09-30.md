# Verification receipt — Quality Gates on the VPS self-hosted runner

- **Task ID:** `infra-actions-self-hosted-vps-2026-09-30`
- **Bot:** `bot-05-infrastructure` (INFRA)
- **Grok run:** `20260930T040531Z-bfab6620`
- **Destructive:** no
- **Secrets committed:** no
- **Approved by:** `bot-06-quality-security` (QUALITY CLEAR_WITH_WAIVERS Path B, tip 1905e44) — see [Approval](#approval)
- **Machine-readable receipt:** [`infra-actions-self-hosted-vps-2026-09-30.json`](./infra-actions-self-hosted-vps-2026-09-30.json)

## Supersedes the first receipt on this branch

An earlier run of this work order pushed commits `9c288e8` and `1af70f9` to this branch and
opened PR #32. That `runs-on` change is correct — byte-for-byte identical to what this run
produced independently — so it is kept as-is rather than re-committed.

Its receipt is what this file replaces. The original JSON carried `bot`, `task`, `claim`,
`evidence`, `rollback`, `destructive` and `secrets_committed`, but none of G-2's five
required fields: `task_id`, `commands`, `claims`, `unverified`, and the `approved_by` the
gate checks for. With no recorded command and no exit code it asserted the change worked
without evidence that anything ran — the exact failure G-2 exists to catch. It would have
failed the gate on five counts at once.

A third revision arrived from a parallel run as commit `8e9d51b` while this one was being
written. Its `approved_by` is not carried forward, and that is a deliberate disagreement
rather than a merge accident — see [Approval](#approval). Its other three findings were
real and are folded into [Not verified](#not-verified): the serial-queue throughput
regression, the extra `ai-cluster` label on the runner registration, and billing being
routed around rather than fixed. Its runner-service check is recorded under
`evidence.service_state` as a second-hand report, because the command embedded the VPS IP
address and neither CI nor this container can re-execute it — and a command nobody can
re-run is not the evidence G-2 asks for.

## Why

The org's GitHub spending limit is exhausted, so every GitHub-hosted job dies in about
three seconds with a spending-limit annotation. Quality Gates never reach their first step,
which means the required checks cannot pass or fail — they simply do not run. A gate that
cannot execute is not a gate.

Ove's GO is to bypass hosted billing by running the gates on the org's own VPS runner
(agent name `srv1778002`, installed at `/opt/actions-runner`), which GitHub does not meter.

## What changed

`runs-on` and nothing else. Five jobs across three files:

| File | Job | Before | After |
| --- | --- | --- | --- |
| `.github/workflows/gates.yml` | `gates` | `ubuntu-latest` | `[self-hosted, Linux, X64]` |
| `.github/workflows/gates.yml` | `gate-self-test` | `ubuntu-latest` | `[self-hosted, Linux, X64]` |
| `.github/workflows/gates-template-sync.yml` | `sync` | `ubuntu-latest` | `[self-hosted, Linux, X64]` |
| `ci/.github/workflows/gates.yml` | `gates` | `ubuntu-latest` | `[self-hosted, Linux, X64]` |
| `ci/.github/workflows/gates.yml` | `gate-self-test` | `ubuntu-latest` | `[self-hosted, Linux, X64]` |

Both leading comment blocks also gained the runner prerequisite, in answer to greptile P1
*Copied gates may never start*. That is the one part of each file the `gates-template-sync`
job excludes from its comparison, so the bodies stay identical.

No gate logic, no Python version, no step body, no trigger and no `permissions` block moved.
Every added or removed content line across both workflow directories is either a `runs-on`
line or a comment line, checked rather than asserted.

## Evidence

Nine commands, all recorded with exit codes in the JSON receipt. The ones that carry the
claims:

- **`DIFF_IS_RUNS_ON_AND_COMMENTS_ONLY changed_lines=31`** — diffed against `origin/main`
  across both workflow directories, every added or removed content line is either a
  `runs-on` line (five removed, five added) or a comment line. Anything else lands in `bad`
  and the assertion fails on a single one, so "nothing executable changed" is checked rather
  than asserted.
- **`RUNS_ON_OK jobs=5`** — all three files parse as YAML and every job's `runs-on` is the
  three-label list. No `ubuntu-latest` survives in either workflow directory.
- **`GATE_BODIES_IDENTICAL lines=131`** — the same comment-block-skipping comparison the
  sync job performs, run locally. Live and template bodies match.
- **`90 passed in 5.13s`** — the gate test suite (`ci/tests/`) is unchanged and still green.
- **G-1 PASS, 3 file(s) within owned paths** — all three workflow files are INFRA's, under
  `.github/workflows/**` and `ci/.github/workflows/**`. No foreign-path carve-out needed.
- **G-3 PASS, no secrets detected** — the runner is addressed by label. No registration
  token, VPS hostname or SSH material appears in the diff.
- **G-5/G-6 PASS** — nothing is deployed and nothing destructive runs. This change edits
  three YAML files and touches no live system.

## The bypass works — observed on the runner

All three workflow jobs have now run on the VPS against the merge head `570037a`. **Two pass
and one fails on the single predicted line** — this is the strongest evidence in the receipt,
and it is observation rather than inference:

| Job | Result | What it settles |
| --- | --- | --- |
| [`gate-self-test`](https://github.com/swcstudiospace/programming-desk/actions/runs/36668189217/job/109737294940) | **success** (18s) | The full 90-test gate suite passes on the VPS, not just in this container. `pip install pyyaml pytest` succeeded against the runner's Python, so it is not an externally-managed system Python that would reject a plain `pip install`. |
| [`sync`](https://github.com/swcstudiospace/programming-desk/actions/runs/36668189235/job/109737295372) | **success** (12s) | The template-sync gate passes in CI, confirming the live and template bodies are still identical after both comment blocks grew. |
| [`gates`](https://github.com/swcstudiospace/programming-desk/actions/runs/36668189217/job/109737295103) | failure (18s) | Fails only at `G-2 — Verification receipt`, on `approved_by`. Everything before it passes on the runner. |

The first observed run, job
[#109735843668](https://github.com/swcstudiospace/programming-desk/actions/runs/36667704256/job/109735843668)
on head `920ce89`, is what retired the three things the first draft of this receipt could not
verify:

- **The runner claimed the job.** The three labels match a real, online runner, so these jobs
  do not sit queued — the failure mode that would have been worst was ruled out by observation.
- **`actions/setup-python@v5` resolved 3.12.14 from the runner's own tool cache** at
  `/opt/actions-runner/_work/_tool/Python/3.12.14/x64`, so it did not have to build Python.
  `pip install pyyaml` and `actions/checkout@v4` both succeeded.
- **The gate steps executed in order.** G-1 manifest, G-1 path ownership and the receipt
  locator all passed, and the locator picked this receipt.

The job's only failure is `G-2 — Verification receipt`, on exactly the line this receipt
predicts:

```
G-2 FAIL — .receipts/bot-05-infrastructure/infra-actions-self-hosted-vps-2026-09-30.json
  - 'approved_by' is missing — work must be reviewed by someone else
```

Two warnings in that log are worth recording and neither blocks: the Node.js 20 deprecation
notice for `checkout@v4` and `setup-python@v5`, which is pre-existing and appears on hosted
runners too; and an `EACCES` stat of `/root/.config/herd-lite/bin/git` during post-job
cleanup, where the runner falls back to `/usr/bin/git` 2.43.0 and the step succeeds. The
second one says the runner executes as a user that cannot read part of root's `PATH` — VPS
tidying, not a gate problem.

## Greptile review — 2 P1 findings

**P1 *Copied gates may never start*
([thread](https://github.com/swcstudiospace/programming-desk/pull/32#discussion_r4140722524)) — fixed.**
The template's leading comment block now makes a matching runner an explicit setup
prerequisite, names the `ubuntu-latest` fallback, and warns that a `runs-on` matching no
runner *queues* rather than fails. Greptile's other option — keep runner selection
configurable per consumer — is not available here: the work order requires the template body
to stay identical to the live workflow and the sync gate enforces it, so the two cannot hold
different `runs-on` values. The comment block is the only part of the file that gate ignores,
which makes it the right place for a consumer setup note.

**P1 security *PR code runs on VPS*
([thread](https://github.com/swcstudiospace/programming-desk/pull/32#discussion_r4140722517)) — valid, not fixed here, escalated to Ove.**
The finding is correct and not disputed. These jobs check out the pull request head and run
its `ci/gates/*.py` and `ci/tests/` on a persistent org host, so a pull request author can
execute arbitrary commands on the VPS before any gate rejects the change, and a
`contents: read` token does not protect the host.

It is inherent to the decision rather than to this diff — you cannot leave GitHub-hosted
runners and keep their ephemeral isolation. Every available fix is outside "only `runs-on`":

| Fix | Why not in this PR |
| --- | --- |
| Re-register the runner `--ephemeral`, or confine it to a container or throwaway user | VPS-side work; appears in no diff. **This is the recommended one.** |
| Add `container:` to both jobs | Changes how every gate step executes — the work order forbids it, and it would risk the green path that job #109735843668 just established |
| Guard on `head.repo.full_name == github.repository` | Leaves a fork's pull request with a required check queued forever — the exact failure mode of the other P1 |

The trade is recorded under [Not verified](#not-verified) and the hardening is documented in
both comment blocks. Choosing it is Ove's call, not INFRA's.

## Rollback

Restore `ubuntu-latest` in all five jobs: `git revert` this change's commit, or edit the
three files back by hand, keeping the live and template bodies identical. Recovery lands on
the next workflow trigger — seconds after the push, since Actions reads `runs-on` fresh per
run and holds no state. No data implications: no deployment, no migration, no cache. The
only effect of reverting is that gate jobs return to the GitHub-hosted queue, where the
spending limit fails them in about three seconds.

## Not verified

The full list is in the JSON. What matters before anyone calls the gates restored:

1. **The gate steps after G-2 have never executed on the VPS** — G-3, G-4 and G-5/G-6, because
   G-2 stops the job before reaching them. They pass in this container, which is not the same
   environment. Everything *before* G-2 is confirmed on the runner, and `gate-self-test` and
   `sync` pass there outright, so this is the only remaining gap in the `gates` job.
2. **Persistent-runner security is accepted and documented, not solved.** See the Greptile
   section. The runner is not known to be `--ephemeral`, nothing here isolates the workspace,
   and it reuses its filesystem between jobs so state leaks from one pull request to the next.
3. **The runner's configuration was never inspected** — this container has no path to the VPS.
   Not whether it is ephemeral, not which user it runs as, not what else shares the host.
4. **Whether `srv1778002` is the only runner carrying these three labels is unestablished.**
   If another org runner matches, gate jobs may land on a host nobody has vetted. The
   registration reportedly also carries an `ai-cluster` label these workflows do not request,
   so the label set is broader than the three used here and nothing pins these jobs to this
   host specifically.
5. **Throughput is a real regression and was not considered.** One runner serves this
   repository serially, so concurrent pull requests queue behind whichever job holds it where
   hosted jobs would have run in parallel. With three open pull requests already wanting
   gates, one slow or hung job delays every other pull request's required checks.
6. **The billing problem itself is untouched.** This routes around the exhausted spending
   limit rather than fixing it, so any workflow still on `ubuntu-latest` keeps failing in
   seconds.

Also: open pull requests **#29** and **#30** are untouched. `pull_request` events read
workflow files from the *head* ref, so both still request `ubuntu-latest` and keep failing
on the spending limit until this change reaches their heads — merge this pull request and
rebase them, or merge `main` into each.

## Approval

`approved_by` is now `bot-06-quality-security` — QUALITY CLEAR_WITH_WAIVERS (Path B local
stamp) on tip `1905e44`, per LEAD ticket to INFRA 2026-09-30. INFRA committed the field
after CLEAR so G-2 can go green; the prior `null` was deliberate until that stamp landed.

Waived Greptile P1 4140722517 (ephemeral isolation / self-hosted runner trust) stays out of
this receipt's claims and is tracked as a separate follow-up draft.

### History (why it was null before CLEAR)

Ove's GO authorised the self-hosted bypass as a *decision*. That is not a review of this
diff, so it stayed in the receipt's `task` field rather than being laundered into
`approved_by` before QUALITY stamped. Commit `8e9d51b` had preset the field while admitting
review had not happened; that premature value was correctly kept out of the merge tip until
CLEAR_WITH_WAIVERS.

Also note: open drafts **#29** and **#30** — #29 tip already carries `runs-on: [self-hosted,
Linux, X64]` on the gate workflows; #30 is MCP+receipts only (no workflow files) per QUALITY
split. #32 remains the source of truth for the runner change on `main` after Ove merge.
