---
name: gsd-runtime
description: >-
  Use when an Omp session plans a prompt: the 25-second handoff, flight
  cancellation, and the outer deadline. Text that is true only on
  fix/omp-planning-cancellation is marked requires claude-ultrathink#34.
---

# gsd-runtime

> Omp native planning, read from `swcstudiospace/claude-ultrathink`. Main is `c8c6290` (after #22–#30 and #32). `fix/omp-planning-cancellation` is `87411ed` ([pull request 34](https://github.com/swcstudiospace/claude-ultrathink/pull/34)), not merged. Apply a paragraph that contains `requires claude-ultrathink#34` only after that pull request is on main.

Under `think.engine: "auto"`, Omp plans on the session's own model inside the Omp process. The extension copies the live model once per flight (`ctx.model`, else `ctx.models.current()`). Selection is a `models.hosts.omp.model` override, else that copy when it can do a plain text completion, else that provider's default. One flight uses one model and Omp's own auth resolver. No tools and no extra headers. A provider error on a stage degrades fail-open. Ship's done check and Teachable Moments stay on the CLI route, outside the flight.

The 25-second race is delivery-only on main and on the branch. A plan ready within 25 seconds is an inline message. A plan still running returns a pending note (read and investigate only: no edits and no mutating commands) and the result arrives later as an aside at a step boundary. Elapsed time at 25 seconds does not cancel the flight.

## On main (`c8c6290`)

Each flight has its own abort controller and a 10-minute outer limit. At that deadline a terminal no-plan result is released even if the provider ignores cancellation, and late output is discarded.

A plan is cancelled and never delivered when you send a newer prompt or an armed `/ultrathink-quick`, when a changed session model is observed at a planning call, an existing agent/turn/tool lifecycle event, or delivery, when a changed thinking level or effective target invalidates reentry, or when you switch or end the session. Cancellation suppresses later stages, tracker calls, state writes, and delivery. An unchanged turn ending, and `session_stop`, do not cancel a deferred plan. A print-mode run (`omp -p`) that exits early cancels its plan.

## requires claude-ultrathink#34

requires claude-ultrathink#34. The default flight has no outer planning deadline. An omitted or zero factory deadline creates no outer timer and no automatic cutoff. The 10-minute cap on main is not the default on this branch.

requires claude-ultrathink#34. The 25-second wait stays delivery-only: pending note, then exactly one aside. It never cancels, lowers effort, changes route, retries, or admits another model call. Removing the default outer timer does not remove `claude.budgetMs` when that budget is configured, the CLI `callTimeoutMs` bounds, or the other hosts' hook limits.

requires claude-ultrathink#34. Coincident handoff callback ordering at the 25-second boundary: if the provider callback runs first, the race is cleared and the plan returns inline with no aside; if the race callback runs first, it dispatches the pending note and the provider result is delivered later as exactly one aside. A completion that wins before the race returns one inline plan and no aside.

requires claude-ultrathink#34. Prompt cancellation still uses the existing events: a newer prompt, an accepted `/ultrathink-quick` message that matches `before_agent_start` (arming one alone is not cancellation), a changed live model, a session switch, or `session_shutdown`. There is no new stop command. A hung provider needs one of those cancellations. Cancellation releases the waiting consumer through the flight's existing outcome even when the provider ignores abort; suppression is already set, so that settlement publishes nothing. A reentrant cancellation of the new flight while the previous abort runs admits no planner and schedules no outer timer.

requires claude-ultrathink#34. Empty FINAL planner output or a no-plan failure before the handoff stays quiet. The same outcome after a pending handoff is exactly one no-plan aside. A handled provider-stage failure can still yield a degraded plan of the stages that worked. A time-expiry terminal no-plan note happens only under an explicit positive factory deadline, which stays opt-in and still discards late output.

requires claude-ultrathink#34. While a flight is still live and no plan or aside has arrived, check three things before resending: the pending note is present, the session is still current, and none of the cancellation events above has fired. Elapsed time alone is not failure, and pending is not proof the provider will finish.
