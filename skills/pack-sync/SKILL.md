---
name: pack-sync
description: Refreshing the desk pack on the box from GitHub main. Use after any merge to main — the mirror is whole-tree, so contracts, scripts, hooks and vendor changes need a sync as much as prompts, skills, ownership.yaml, gates and docs do — and on first install of the pack on a box. Use before any operation that would copy pack contents back toward GitHub — to stop it.
bots: [bot-05-infrastructure, bot-00-programming-lead, all]
gates: [G-2, G-6]
---

# Pack Sync

## L1 — Summary

**GitHub `main` is the source of truth. The pack on the box is a mirror of it, and mirrors do not
write back.**

The pack currently installed is **stale six-bot** — it predates the seven-seat roster. Where it
disagrees with `main`, it is out of date, not in dispute. Sync runs one way, after a merge, from a
clean clone: `main` → pack. There is no reverse direction and no small-edit exception.

**Decision tree:**

```
About to touch the pack or the repo because the two differ?
│
├─ Would the change move content from the pack toward GitHub?
│   │  (push from the pack, copy pack files into a clone, "restore box state" PR,
│   │   resolving a conflict in the pack's favour, citing pack files as evidence)
│   └─ YES ──▶ STOP. Never. Re-author it as a normal PR against main. §3
│
└─ Moving main → pack.
    │
    Has the change merged to origin/main?
    ├─ NO ──▶ Not yet. Unmerged work is not source of truth. §1
    └─ YES
        │
        Is your clone clean AND is HEAD equal to origin/main?
        ├─ NO ──▶ Resolve that first. A dirty clone — or one carrying an
        │         unpushed commit — is not a mirror source. §2
        └─ YES ──▶ Verify, then mirror, then write the receipt. §2, §4
                   Overwriting a live pack is G-6 — approval first. §4
```

**The one-line test:** if this sync were re-run from a fresh clone of `main` tomorrow, would the box
end up in the same state? If not, something on the box is unreviewed — §3, not a push.

Full procedure with commands: [`../../docs/pack-sync.md`](../../docs/pack-sync.md).

---

## L2 — Method

### §1 When to run

| Trigger | Run |
|---|---|
| **Any** merge to `main` | Yes, after the merge commit is on `origin/main`. The mirror is whole-tree, so a path-shaped trigger list strands `contracts/**`, `ci/hooks/**`, `scripts/**` and `vendor/**` |
| First install of the pack on a new box or agent workspace | Yes |
| Open draft PR you expect to merge | No — sync after it merges |
| Pack "looks wrong" mid-task, or a gate fails on the box | No — fix it in a PR against `main`, then sync |
| Scheduled / cron | No. It races open PRs and re-installs the pack under a running job |

### §2 The sync itself

`docs/pack-sync.md` §4 carries the commands. The shape:

1. **Pull.** `fetch origin main`, `checkout main`, `merge --ff-only`. Record the SHA.
2. **Prove the clone is clean *and level*.** `git status --porcelain` empty, and `rev-parse HEAD`
   equal to `rev-parse origin/main`. `--ff-only` says "Already up to date" and exits 0 when local
   `main` is *ahead*, so a clean status alone would ship an unpushed, unreviewed commit to the box
   and record its SHA as if GitHub had it.
3. **Prove `main` is self-consistent.** Manifest validates, gate tests pass, `assemble-prompts.sh`
   leaves no diff. Mirroring a broken `main` installs it everywhere at once.
4. **Mirror tracked content only.** `git archive HEAD` into a staging tree, then
   `rsync --delete --exclude '.git/' --exclude '.receipts/'` from it — dry run first, reading the
   deletion list **at a stop, not in passing** — the script gates between the dry run and the real
   run, so a pack-only edit can still be rescued (§5) instead of merely reported. Rsyncing the clone
   itself would carry gitignored artefacts (`.venv/`,
   `__pycache__/`, `.pytest_cache/`, the caches step 3 just created) onto a shared box; without
   `--exclude '.receipts/'`, `--delete` erases the box's receipt history — the evidence for every
   earlier sync; without `--exclude '.git/'` it erases the pack's own git history if the pack is a
   checkout. Run it as a script under `set -euo pipefail` with the stage guards from
   `docs/pack-sync.md` §4.3: an empty `STAGE` makes the rsync source `/`, and a failed `git archive`
   still leaves `tar` exiting 0, so either one turns `--delete` into "empty the pack".
5. **Receipt** naming the mirrored SHA, written **outside** the pack root: anything inside is
   overwritten by the next sync.

The claim a sync receipt supports is **"the pack mirrors `main` at `<sha>`"**. It does not claim the
pack works, that agents picked the change up, or that anything was restarted — those go in
`unverified` unless you ran something that proves them.

### §3 Never: pack → GitHub

| Attempt | What it actually does |
|---|---|
| `git push` from the pack | Re-installs superseded six-bot state over reviewed state |
| Copy pack files into a clone and commit | Produces a restore disguised as a change; silently reverts merged PRs |
| "Sync from pack" / "restore box state" PR | Has no reviewable authority behind it |
| Deciding a main-vs-pack conflict for the pack | The pack has no review history; `main` is the only reviewed record |
| Pack contents as receipt evidence | Box state is not re-runnable, so it is not G-2 evidence |

**Drift worth keeping** is not an exception — it is a normal change. Read the edit out of the pack,
re-author it on a branch from a clean clone, open a draft PR under the right `ownership.yaml` owner,
merge, then sync. Read it out *before* syncing: §2 step 4 deletes it.

### §4 Approval and blast radius

Overwriting a live pack on the shared box changes what every agent on that box loads next. That is a
destructive operation on shared state — G-6, recorded approval, per
[`../platforms/remote-dev-machine/SKILL.md`](../platforms/remote-dev-machine/SKILL.md) §3.

A running agent's `SYSTEM_PROMPT.xml` under `/home/box/agent-data/agents/<uuid>/` is outside the pack
root and is its own decision with its own approval. Do not fold it into a pack sync silently: say in
the receipt whether you touched it.

### §5 Checklist

- [ ] The change is merged to `origin/main` — not an open PR
- [ ] Syncing from a clean clone, not from the pack directory
- [ ] `rev-parse HEAD` == `rev-parse origin/main` — no unpushed commit riding along
- [ ] `check_ownership.py --validate-manifest` passes on the source tree
- [ ] `pytest ci/tests/` passes on the source tree
- [ ] `assemble-prompts.sh` leaves no diff on the source tree
- [ ] Mirroring a `git archive HEAD` export, not the working directory
- [ ] Running as a script under `set -euo pipefail`; stage guards present, so no failure upstream of
      `rsync --delete` can reach it
- [ ] `--exclude '.receipts/'` present so `--delete` cannot erase receipt history
- [ ] `--exclude '.git/'` present so `--delete` cannot erase the pack's own git history
- [ ] `rsync` dry run read at the gate, deletion list understood, before the real run was authorised
- [ ] G-6 approval recorded before overwriting a live pack
- [ ] Receipt written outside the pack root, names the mirrored SHA; unverified lists what was not
      restarted or checked
- [ ] Nothing moved pack → GitHub in any form

## What this skill does not do

- It does not authorize writing to the box. §4 approval is separate and comes first.
- It does not verify the pack's live path or contents — `docs/pack-sync.md` leaves `<PACK_ROOT>` a
  placeholder deliberately.
- It does not make the pack a review surface. Review happens on `main`.
- It does not cover Agent Bus, CI workflows or the Greptile gate.
