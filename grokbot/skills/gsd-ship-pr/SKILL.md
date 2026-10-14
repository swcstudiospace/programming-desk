---
name: gsd-ship-pr
description: >-
  Use when a GSD or ultrathink ship opens or reviews a pull request. States the
  plugin ship path on claude-ultrathink main, the review-only Grok Bot path, and
  that Ming's VPS keeps ship.autoMerge and ship.deleteBranch on.
---

# gsd-ship-pr

> Synced to `swcstudiospace/claude-ultrathink` `skills/ultrathink-ship/SKILL.md` and `docs/ship.md` at `c8c6290` (main after #22–#30 and #32). Pull request #34 does not change ship. This file has no sentence that depends on claude-ultrathink#34.

## Ming's VPS

On Ming's VPS, `ship.autoMerge` and `ship.deleteBranch` stay on. This skill does not change those keys.

With both on, a ship that passes the merge gate merges with config `mergeMethod` (squash by default) and then deletes the remote branch and the local branch. The gate is a completed Greptile review of the exact PR head at score >= `ship.minScore` (default 5) with no open threads, an open mergeable PR, and CI neither pending nor failing. With `ship.autoMerge` on, a Jev-only verdict never counts as the judge: without a usable judge verdict the result stays not done.

The published default in upstream `docs/ship.md` is off for both keys. That default is not the VPS setting.

## Two hosts

Plugin hosts (Claude Code, Omp, Hermes, Muse, Grok Build) run `bin/ultrathink-ship` when `ship.enabled` is true. The state file is the session record. Steps are idempotent: reuse an open PR, reuse a review of the same head, and detect an already-merged PR.

Grok Bot on the desk always runs `ultrathink-grokbot` with `ULTRATHINK_SHIP=0`. Its `ultrathink-ship` skill is review-only: `G review read` returns the score and open Greptile threads, the owning agent fixes them, and a stale review is retriggered with one `@greptileai` comment only after Ming approves that post. At 5/5 with no open threads and green checks, tell Ming the PR is ready. The bot does not call `ship pr`, `ship merge`, or `ship run`. That host rule is `ULTRATHINK_SHIP=0`. It is not an edit to the VPS keys above.

Programming Desk work in this repository still opens a draft pull request and is not merged from the desk. That is the desk operating model. It is not an edit to the VPS keys.

## Plugin ship order

1. `assess`. Gate mode (`ship.judge: "gate"`, the default): if `done` is false, or a GSD phase verification is `human_needed` or `gaps_found`, or the roadmap still has incomplete phases, do not open a PR. Advisory mode: `done` is the deterministic rules; finish concrete missing work inside this task, then continue. `--ignore-gsd` only after the user has said the repository's GSD roadmap is separate work.
2. Commit only this task's files, by explicit path.
3. `pr` pushes the branch and opens or reuses a PR into the default branch read from GitHub.
4. `git push`, then `review`. Pending is not a round. `unverified` retries the thread scan without a new round. A failed or timed-out review is retried up to `ship.reviewRetries` (default 3) and does not count toward `maxRounds`. `needs-fixes` is fixed in greploop order (security, then P0, P1, P2), committed as `address greptile review feedback`, pushed, and reviewed again. Resolve a thread only when the finding is factually wrong or intended. Stop on `blocked` or two consecutive rounds with identical findings.
5. `merge` checks the same gate and retries inside `ship.waitMs` for pending CI, mergeability not yet computed, unreadable PR state, and transient GitHub errors. `waiting: true` means run `merge` again. Past `ship.mergeTimeoutMs` (60 minutes) on one head, the ship blocks. Conflicts, failing CI, a moved head, or a review below 5/5 go back to the agent.
6. Record the PR with `ultrathink-sync`, using the `plan.graphId` captured when this ship started.
7. Report the PR URL, review rounds, final score, and whether it merged.

From review round 3, repeated findings of one shape use [`ultrathink-pstack`](../ultrathink-pstack/SKILL.md) §5.

Never lower the bar, and never merge by another command.
