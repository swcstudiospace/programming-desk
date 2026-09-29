# Pack Sync — main → pack, one direction only

**Audience:** whoever refreshes the desk pack installed on the shared dev box (INFRA by default; LEAD
when it follows a merge it orchestrated).
**Status:** Runbook recorded. **Not executed while authoring.** No live pack was read or mutated in
the session that wrote this file, so every path under `<PACK_ROOT>` below is a placeholder to resolve
on the box, not a verified location.

Companion docs: seats and tickets — [`desk-operating-model.md`](./desk-operating-model.md);
GitHub as contract of record — [`github-sot-orchestration.md`](./github-sot-orchestration.md);
gates — [`quality-gates.md`](./quality-gates.md). Box safety rules —
[`../skills/platforms/remote-dev-machine/SKILL.md`](../skills/platforms/remote-dev-machine/SKILL.md).
The trigger conditions and the stop conditions live in
[`../skills/pack-sync/SKILL.md`](../skills/pack-sync/SKILL.md).

---

## 1. The direction rule

**GitHub `main` in `swcstudiospace/programming-desk` is the source of truth. The pack is a
read-only mirror of it.**

| Layer | Role | Never |
|---|---|---|
| **GitHub `main`** | Source of truth for the seven-seat desk: prompts, ownership manifest, gates, skills, docs | Updated from the pack |
| **Box pack** (`<PACK_ROOT>` on the dev box) | Runtime copy the agents load | Treated as authority when it disagrees with `main` |

The pack currently on the box is **stale six-bot**: it predates the seven-seat roster (LEAD plus six
specialists, QUALITY off-channel — see `docs/desk-operating-model.md`). Everything in it that
disagrees with `main` is out of date by construction, not a competing opinion.

**Why one direction.** A two-way sync has no tiebreak. The moment the pack can write back, the
answer to "what does this desk actually run" depends on who copied last, `ownership.yaml` stops being
the single owner map, and G-1 attributions become unreviewable — the change arrives with no branch,
no PR, no receipt and no acting bot. A one-way mirror keeps every change to the desk on the record:
branch → draft PR → review → merge → sync.

## 2. Forbidden — pack → GitHub

These are the operations this runbook exists to prevent. Each one is a hard stop, not a judgement
call.

| Do not | Because |
|---|---|
| `git push` from `<PACK_ROOT>` to any branch of this repo | The pack is stale six-bot; a push re-installs superseded state over reviewed state |
| Copy pack files over a clone's files, then commit the result | The diff is a restore, not a change. It silently reverts merged PRs and nobody can tell which |
| Open a PR whose body is "sync from pack" or "restore box state" | There is no authority behind it to review against |
| Resolve a main-vs-pack disagreement in the pack's favour | The pack has no review history. `main` is the only reviewed record |
| Regenerate `prompts-assembled/` from pack copies | Assembly runs from `prompts/` in a clean clone (`scripts/assemble-prompts.sh`) or the six-bot set leaks back in |
| Cite pack contents as evidence in a receipt or a merge claim | Uncommitted box state is not reproducible. G-2 evidence must be re-runnable |

**There is no exception for a small edit.** A one-line fix on the box is still a change with no
review trail. §5 says what to do with it instead.

## 3. When to sync

Sync **after** a merge lands, never in anticipation of one.

| Trigger | Sync |
|---|---|
| A PR merged to `main` touching `prompts/**`, `skills/**`, `ownership.yaml`, `ci/gates/**` or `docs/**` | Yes — after the merge commit exists on `origin/main` |
| First install of the pack on a new box or a new agent workspace | Yes — clean clone, no mirror step needed beyond §4 |
| An open draft PR you expect to merge | **No.** Unmerged work is not source of truth |
| The pack "looks wrong" mid-task | **No.** Finish or stop the task, then sync from a merge |
| A failing gate on the box | **No.** Fix the gate in a PR against `main`, then sync |

Do not put this on a cron. A scheduled sync races open PRs and re-installs the pack mid-job for
whatever is running on the box.

## 4. Procedure

Run from a **clean clone**, not from `<PACK_ROOT>`.

### 4.1 Pull main

```bash
git -C <CLONE> fetch origin main
git -C <CLONE> checkout main
git -C <CLONE> merge --ff-only origin/main   # fails loudly rather than creating a merge commit
git -C <CLONE> status --porcelain            # must be empty; a dirty clone is not a mirror source
git -C <CLONE> rev-parse HEAD                # record this SHA — it is what the pack is at
```

A non-empty `status --porcelain` or a failed `--ff-only` means the clone carries local state. Stop and
resolve that first; mirroring from it copies unreviewed edits onto the box.

### 4.2 Verify the source before mirroring

```bash
cd <CLONE>
python3 ci/gates/check_ownership.py --validate-manifest
python3 -m pytest ci/tests/ -q
./scripts/assemble-prompts.sh && git status --porcelain prompts-assembled prompts
```

The last line must print nothing: assembled prompts on `main` already match their sources. If it
prints paths, `main` is out of sync with its own generator — fix that in a PR before touching the
pack.

### 4.3 Mirror into the pack

Copy `main`'s tree into `<PACK_ROOT>`, deleting pack-only leftovers so the six-bot residue goes with
them. Dry-run first, always:

```bash
rsync -avn --delete --exclude '.git/' <CLONE>/ <PACK_ROOT>/   # -n: dry run, read the deletions
rsync -av  --delete --exclude '.git/' <CLONE>/ <PACK_ROOT>/
```

Read the dry-run deletion list before the real run. Anything listed for deletion that you wanted to
keep is a local edit — §5, not a reason to drop `--delete`.

Runtime agents load their system prompt from `/home/box/agent-data/agents/<uuid>/SYSTEM_PROMPT.xml`
(`ARCHITECTURE.md` §7), which is outside `<PACK_ROOT>`. Refreshing that file is a separate step with
its own approval — a running agent's prompt changing under it is a G-6 destructive operation on a
shared box.

### 4.4 Record the sync

Write a receipt under `.receipts/<bot-id>/<task_id>.json` per
[`../skills/verification-receipts/SKILL.md`](../skills/verification-receipts/SKILL.md): the commands
above with their exit codes, the `main` SHA the pack now mirrors, and anything you could not verify
(a running agent not restarted, a prompt file left untouched) in `unverified`.

The claim the receipt backs is **"the pack mirrors `main` at `<sha>`"** — not "the pack is correct".

## 5. Pack drift you want to keep

A local edit on the box that is genuinely worth having is a change to `main`, and it takes the same
route as any other:

1. Read the edit in the pack. Do not copy the file.
2. Re-author it on a branch in a clean clone, against current `main`.
3. Open a draft PR. Owner comes from `ownership.yaml`; the receipt comes from the skill above.
4. Merge, then sync — §4 overwrites the box copy with the reviewed one.

The pack copy is discarded at step 4, and that is the point: the surviving version is the one that
was reviewed. A sync performed before the PR merges loses the edit, so read it out first.

## 6. Gates this touches

| Gate | Here |
|---|---|
| **G-1** | Pack sync changes no repo paths. A PR *about* sync obeys `ownership.yaml` like any other — `docs/**` and `skills/**` are QUALITY's |
| **G-2** | The sync claim needs a receipt naming the mirrored SHA (§4.4) |
| **G-6** | Overwriting a live pack on a shared box, or a running agent's prompt, is destructive and needs recorded approval. See `skills/platforms/remote-dev-machine/SKILL.md` §3 |

## 7. Parity with ship-desk

Thin notes only. The conventions below are the ones this desk and ship-desk hold in common, recorded
so a reader moving between them knows what carries over. **No ship-desk file was read while writing
this, and none is copied here** — treat the mapping as unverified and confirm against that repo
before relying on it.

| Convention | Here | Carries over as |
|---|---|---|
| One-way sync | `main` → pack; pack never writes back | The same direction rule, whatever the mirror's name |
| Runbook lives with the repo it syncs | `docs/pack-sync.md` | A runbook in the source-of-truth repo, not on the box |
| Trigger is a merge | §3 | Post-merge sync, never scheduled and never pre-merge |
| Evidence | Receipt naming the mirrored SHA | Some re-runnable record of which commit the mirror is at |
| Drift | Re-authored as a PR, never pushed from the mirror | Same |

What does **not** carry over without checking: seat names and counts, path ownership, gate ids, and
branch-prefix conventions. Those are per-desk and copying them across is how a stale roster spreads.
Where ship-desk and this desk disagree on any of them, this repo's `ownership.yaml`, `docs/quality-gates.md`
and `docs/desk-operating-model.md` govern work in this repo.

## 8. What this runbook does not do

- It does not authorize any write to `<PACK_ROOT>` on its own. §6 G-6 still applies.
- It does not verify the live pack's contents, layout or path. Those are unresolved placeholders.
- It does not describe the Agent Bus, CI workflows or the Greptile gate — see their own docs.
- It does not make the pack reviewable. The pack is a copy; review happens on `main`.
