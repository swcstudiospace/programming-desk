# Verification receipt — Quality Gates on the VPS self-hosted runner

- **Task ID:** `infra-actions-self-hosted-vps-2026-09-30`
- **Bot:** `bot-05-infrastructure` (INFRA)
- **Grok run:** `20260930T040531Z-bfab6620`
- **Destructive:** no
- **Secrets committed:** no
- **Approved by:** *nobody yet* — see [Approval](#approval)
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

No gate logic, no Python version, no step body, no trigger and no `permissions` block moved.
The distributable template changed in step with the live workflow, so the two stay
body-identical after their leading comment blocks — which is the only thing the
`gates-template-sync` job compares.

## Evidence

Nine commands, all recorded with exit codes in the JSON receipt. The ones that carry the
claims:

- **`DIFF_IS_RUNS_ON_ONLY changed_lines=10`** — diffed against `origin/main` across both
  workflow directories, every added or removed content line is either the old
  `ubuntu-latest` line or the new self-hosted line. Five removed, five added. Any other
  edited line would have tripped the assertion, so "only `runs-on`" is checked rather than
  asserted.
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

## Rollback

Restore `ubuntu-latest` in all five jobs: `git revert` this change's commit, or edit the
three files back by hand, keeping the live and template bodies identical. Recovery lands on
the next workflow trigger — seconds after the push, since Actions reads `runs-on` fresh per
run and holds no state. No data implications: no deployment, no migration, no cache. The
only effect of reverting is that gate jobs return to the GitHub-hosted queue, where the
spending limit fails them in about three seconds.

## Not verified

The full list is in the JSON. The four that matter before anyone calls the gates restored:

1. **No Actions run has executed on the VPS runner from this change.** A runner picking up
   a job, checking out and completing a gate step was never observed from this container.
2. **`srv1778002`'s labels were not inspected.** If it does not carry all three of
   `self-hosted`, `Linux` and `X64`, these jobs *queue* rather than fail — which presents as
   a required check pending forever, not as an error. Confirm the labels on the runner.
3. **`actions/setup-python@v5` was not exercised on the VPS.** On a hosted image it resolves
   3.12 from the pre-seeded tool cache; a self-hosted runner without that cache downloads
   and builds it, needing build tooling and outbound network. Likewise the unchanged
   `pip install pyyaml` steps run against whatever Python the runner exposes — an
   externally-managed system Python would reject a plain `pip install`.
4. **Persistent-runner posture is Ove's call, not INFRA's.** These workflows check out the
   pull request head and `pip install` on a runner that reuses its filesystem between jobs.
   For a private repo with trusted bots that is the accepted trade for having gates at all,
   but it is a genuine change in blast radius from an ephemeral hosted VM, and nothing here
   isolates the workspace.

Also: open pull requests **#29** and **#30** are untouched. `pull_request` events read
workflow files from the *head* ref, so both still request `ubuntu-latest` and keep failing
on the spending limit until this change reaches their heads — merge this pull request and
rebase them, or merge `main` into each.

## Approval

`approved_by` is deliberately `null`, so **G-2 fails on this receipt**, and that missing
independent approval is the only thing it fails on. Everything else in the receipt is green.

Ove's GO authorised the self-hosted bypass as a *decision*. That is not a review of this
diff, so it is recorded in the receipt's `task` field rather than laundered into
`approved_by`. This follows
[`claude-mcp-json-hindsight-20260930T023348Z-239b2b18.json`](./claude-mcp-json-hindsight-20260930T023348Z-239b2b18.json),
which emptied the same field after greptile P1 4140306040 correctly called a
named-but-absent reviewer a recorded approval that never happened.

QUALITY (`bot-06-quality-security`) or Ove stamping `approved_by` is what turns G-2 green.
Nothing else in the receipt has to change.
