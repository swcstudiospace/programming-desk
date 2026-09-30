# Desk Operating Model — Seven-Seat Programming Desk

Programming Lead sits **in** the Programming Desk channel and orchestrates. The six members are
LEAD, SYSTEMS, WEB, ANDROID, IOS, and INFRA. QUALITY is off-channel for post-build merge-gate
(platform max 6). Lead + six specialists = seven-seat desk.

```
Ove ──1:1──▶ LEAD (in channel; reports to Ove 1:1)
              │
              ├──SendToAgent 1:1──▶ build seats (SYSTEMS WEB ANDROID IOS INFRA)
              │                         │
              │                         ├── human-visible traffic ──▶ Desk channel
              │                         └── held handoff (priority false) ──▶ LEAD polls
              │
              ├── required dispatch note ──▶ Desk channel
              │
              ├──SendToAgent 1:1──▶ QUALITY (off-channel)
              │                         └── status priority false ──▶ LEAD relays into Desk
              │
              └── report to Ove (1:1)
```

## Flow

For a real build, fix, research, or change, intake is the dense GoTxCoT path in
`docs/gotxcot-cloud-pipeline.md` and `skills/gotxcot-uplift` — not a short paraphrase.

1. **Drop prompt in** — Ove messages LEAD with the plain ask.
2. **First uplift** — LEAD rewrites it into long nested XML (`BUILD_PROMPT` / `FIX_PROMPT` / `RESEARCH_PROMPT` / `CHANGE_PROMPT` / `UPLIFTED_PROMPT`).
3. **GoT + CoT** — **5–8 nodes**, then **4–8 CoT steps per node**, one node at a time unless parallel fill is safe.
4. **Trackers** — Notion Agent Task Graph (Task → Issue → Sub-Issue) and Linear (one issue per node, one sub-issue per step). `Agent` = `cursor-cloud` when Cloud Agents execute.
5. **Second uplift** — the same XML, extended with `<ISSUES>` and live Notion/Linear URLs.
6. **Dispatch** — `skills/trackplan-dispatch` to Cursor Cloud Agent (default) or Hermes. Lane C specialist tickets (below) still carry the relevant issue/sub-issue URLs.
7. **Implement** — Specialist executes only assigned work in owned paths; writes a receipt. Specialists do not re-run uplift.
8. **Receipt** — The build seat posts the summary into the Desk with the explicit label `awaiting-review / pending QUALITY`, and sends LEAD a held handoff (priority false) with the receipt path. LEAD checks held messages at the start of every turn and after Desk activity.
9. **QUALITY** — LEAD requests review 1:1 when a completion claim needs an independent check, including the Greptile merge gate on the PR. QUALITY replies to LEAD priority false. LEAD relays that status into the Desk.
10. **Consolidate / report** — LEAD reports to Ove 1:1. A Desk completion that still says `awaiting-review / pending QUALITY` is not clearance. Build seats do not invent work from desk-channel vibes.

A small, already-scoped ask may skip straight to a Lane C ticket when LEAD records why a full graph is not warranted (trivial ack, single-file question already answered). Real build tasks do not skip the 5-node minimum.

## The production loop (steps 7–8, every seat, every ticket)

Steps 7 and 8 above are not freeform. Every seat runs one turn shape, on every ticket, in both
Lane C and the dispatched lanes:

```
memory_brief (+ etag) ──▶ act ──▶ memory_write ──▶ events_emit ──▶ handoff_to_hermes (only if the ticket hands off)
```

The procedure, the tool-name mapping onto the gateway's `desk_*` equivalents, and the failure modes
are in [`../skills/desk-bootstrap/desk-production-loop/SKILL.md`](../skills/desk-bootstrap/desk-production-loop/SKILL.md),
which is enabled on all seven seat templates. Six points are desk policy rather than skill detail:

1. **No repo work before a brief that succeeded, and success is judged on the nested error fields.**
   Reading files is fine; editing, committing, branching, pushing, opening a PR, or any `write` tool
   call waits for the brief. A seat that edits first is re-deciding something already recorded in the
   memory plane it skipped. **A populated response is not a successful brief**: `desk_brief` returns
   its full shape even when the substrate is unreachable, there is no top-level `reason`, and the
   failure sits in `substrate.error` or `recall.error`. Those two fields plus "the tool was listed and
   the call was not deadline-cut" are the whole test. A seat that checks only the envelope reads an
   outage as a quiet ticket.
2. **Record what you read, and claim no more than the tool supports.** Where a tool's contract carries
   an etag, the receipt records `brief_etag` and change detection is real. `desk_brief` carries none,
   so the receipt records `brief_read_at` (its `generated_at`) **and** `cached`, and the seat states in
   `unverified` that it could not tell whether the brief changed under it. `generated_at` is a read
   timestamp, not a revision id: it moves on every fresh call whether or not memory changed, and a
   cache hit carries the original assembly time for up to five minutes after memory changed — so it is
   never recorded as `brief_etag` and never diffed. **Absence of an etag field is not degradation**;
   reading it that way would make a human ack the price of every ordinary turn on the desk.
3. **Degraded mode needs a human ack.** Degraded means the brief *failed* per point 1 — `substrate.error`
   or `recall.error` present, the tool unlisted, the call deadline-cut, or an etag-bearing tool
   returning no etag. Those are *unknown*, never *none*. Working the repo anyway needs a recorded
   acknowledgement, routed the way approvals already are: a build seat asks LEAD priority false; LEAD
   asks Ove in the 1:1. The ack id goes in the receipt's `approvals` with the verbatim nested reason and
   its field path in `unverified`, it covers one turn on one ticket, it is not a g5/g6 `approval_id`,
   and it is never typed by the seat that needs it. No ack is a blocker, and a reported blocker is a
   finished turn.
4. **Degradation is signalled in the event payload, never by swapping the event kind.** A degraded
   turn that got its ack and finished the work still emits `implementation.completed` with the receipt
   path, plus `payload.degraded: true` and the ack id. `ticket.blocked` is for the turn that *stopped*
   — no ack, or ack refused. `docs/handoff-contracts.md` routes on kind, so a finished turn labelled
   `ticket.blocked` sends LEAD chasing a blocker for work that is sitting ready for review.
5. **Docs and memory only through the substrate or the gateway.** No seat default calls a raw
   RAGFlow or Hindsight server (`user-ragflow`, `user-hindsight`, or a direct MCP/HTTP endpoint):
   that path needs a credential the seat must not hold, leaves no event row, and can retain outside
   `pd-<seat>`.
6. **Skills are listed and invoked only.** A seat does not install, enable, edit, publish or approve
   a skill — for itself or another seat — until a `skills.approve` capability exists. `skills_propose`
   opens a PR; a proposal is not an installed skill.

`handoff_to_hermes` is expected to carry a signed packet so a receiving runtime can verify the desk
issued it. That schema is SPE-4792's and has not landed, so the packet fields are a documented stub:
they are omitted, never fabricated, and a handoff made in the meantime is recorded as unsigned in
the receipt's `unverified`.

## Lane C ticket flow

1. **Intake** — goal, constraints, and success criteria are already in the second uplift when the graph ran.
2. **Ticket** — LEAD writes one concrete ticket per owning seat (see format below).
3. **Dispatch** — LEAD `SendToAgent` to each seat 1:1 (never vague "please help").
4. **Implement** — Specialist runs the production loop above: a brief that succeeded on its nested error fields before the first edit, then executes only assigned work in owned paths, and writes a receipt.
5. **Receipt** — Build seat posts into the Desk labeled `awaiting-review / pending QUALITY` and sends LEAD a priority-false handoff. LEAD polls held messages; they do not wake LEAD by themselves.
6. **QUALITY** — LEAD requests review 1:1. QUALITY is off-channel and returns status priority false. LEAD relays it into the Desk.
7. **Consolidate** — LEAD consolidates specialist receipts + QUALITY verdict.
8. **Report** — LEAD reports to Ove. Specialists do not invent work from desk-channel vibes.

Cross-seat features: **contract-first via QUALITY**, then parallel tickets
(`docs/cross-bot-protocol.md`). LEAD is the integrating orchestrator who opens the work and
consolidates — not the implementer.

## Ticket format

```markdown
## Ticket

- **task_id:** feat-push-notifications-android
- **owner:** bot-03-android (ANDROID)
- **goal:** Register FCM device tokens and display data-message notifications per contract v1.4.0
- **paths_in_scope:**
  - android/app/src/main/**/notifications/**
  - android/app/src/test/**/notifications/**
- **out_of_scope:**
  - Backend send API (SYSTEMS)
  - iOS APNs (IOS)
  - Infra credentials (INFRA) unless this ticket says otherwise
- **trackers:** (when a graph exists) Graph ID, Notion Issue/Sub-Issue URLs, Linear issue/sub-issue URLs from the second uplift. Do not paste the entire XML into chat if the packet already lives on the branch; cite it.
- **success_criteria:**
  - Unit tests for token registration pass (`./gradlew :app:testDebugUnitTest`)
  - Receipt at `.receipts/bot-03-android/<task_id>.json` with cited commands and the brief record (`brief_etag`, or `brief_read_at` + `cached`)
  - No owned-path violations (G-1)
  - Production loop run: brief before the first edit, `memory_write` and `events_emit` in the same turn (or a recorded degraded-mode ack)
- **report_back:**
  - Receipt path
  - Summary of files changed
  - `unverified` list (devices / OS versions not exercised)
  - Blockers for LEAD (if any)
```

## Channel rules

Full human-visible traffic belongs in the Desk for build seats: status, progress, blockers,
questions, numbered options, and labeled completions. The channel is not the assignment bus.

| Actor | Channel | What they post | How work arrives |
|---|---|---|---|
| LEAD | Member | Required dispatch note after every assignment; QUALITY status relay; widget-selection echo. Reports to Ove in the LEAD↔Ove 1:1. | Ove messages LEAD 1:1. LEAD polls held seat→LEAD messages at the start of every turn and after Desk activity. |
| SYSTEMS, WEB, ANDROID, IOS, INFRA | Members | Full human-visible traffic: status, progress, blockers, questions, numbered options, and completion posts labeled `awaiting-review / pending QUALITY`. | Tickets via SendToAgent 1:1. Structured handoffs to LEAD are priority false. |
| QUALITY | Off-channel | Does not post into the Desk. Sends review status to LEAD priority false. | LEAD tickets 1:1 after the build. |
| Ove | Messages LEAD 1:1 | Primary operator interface. Sees a true widget only in the LEAD↔Ove chat. | — |

If a build seat is woken by a desk-channel ping with **no LEAD ticket**: say so in the Desk and
SendToAgent LEAD priority false. Do not invent work.

## Verification

LEAD never fabricates specialist receipts. "Done" to Ove requires consolidated specialist
receipts and QUALITY approval when review was requested. Honest `unverified` lists are success;
silent incompleteness is not (PD-1, PD-6).

## Merge-claim head rule

A merge-claim receipt names the commit Greptile COMPLETED and does not claim CLEAR or
CLEAR_WITH_WAIVERS for a later tip that review did not cover. `merge_claim.allowed` stays
false and the verdict stays BLOCKED until Greptile's status on that tip is COMPLETED and
QUALITY stamps `approved_by`. Until that stamp, `approved_by` stays empty and G-2 fails closed.

SKIPPED is not a pass. Do not send LEAD back to review an older SHA after the branch has moved.
The pending target is the tip of `cursor/desk-human-visible-surface-101e` that contains this
section. Parent at authoring: `ddc113bcd20e6b59e30060db1f863ea39d25a8ca` (COMPLETED 4/5; that
score is not a score for this tip). Do not re-request review of
`c5c8b5ee68b31c960af90415497b5147527964cc`.

Claims cite `evidence_command_index`, the field G-2 reads. A waiver whose status is
`DOES_NOT_COVER_CURRENT_HEAD`, or whose live stamp is `WITHDRAWN`, is not an active waiver
and is not an unchanged historical waiver. This file cannot store the SHA of the commit that
adds it; writing that SHA would change it.

## Channel roster

Members (6): LEAD, SYSTEMS (Systems & Design), WEB (Web & Desktop), ANDROID (Android & Play Release), IOS (iOS & App Store), INFRA (Infra & WEB3).

Off-channel: QUALITY (Quality & Security) — Greptile merge-gate, security review, and `approved_by` via LEAD 1:1 after the build. LEAD relays human-visible QUALITY status into the Desk.

Live host membership for this policy is already LEAD in and QUALITY out. This document matches that roster.

## Channel discipline (human-visible surface)

Ove messages **LEAD** 1:1. LEAD reports to Ove in that 1:1 and may post audit notes into the Desk.

The five build seats post **only** into Programming Desk (`4d78b294-5b65-46a9-bec9-86cdbc54aa3e`) for anything Ove should see: status, progress, blockers, completion summaries, questions, and selectable options. A completion post contains the explicit label `awaiting-review / pending QUALITY`. That label is not clearance.

QUALITY does not post into the Desk. QUALITY sends status to LEAD priority false, and LEAD relays it.

Platform limit: widgets/cards do **not** render in group rooms. Numbered choices are plain text in the Desk. When a true widget is required, the build seat asks LEAD (priority false). LEAD shows the widget in the LEAD↔Ove 1:1. LEAD then posts the selection into the Desk **and** SendToAgent the asking seat priority true. The seat continues from that message.

Assignment remains LEAD → seat via 1:1 `SendToAgent`. LEAD is in the channel; the Desk is still not the assignment bus. The dispatch note in the Desk is required after every assignment.

Structured handoffs seat → LEAD use `priority: false` (held; Ove does not see them). LEAD must check those held messages at the start of every turn and after Desk activity. A priority-false message does not wake LEAD by itself.

If Ove messages a build seat directly, that seat sends LEAD a held plan and waits for LEAD's plan **before editing**. It does not do the work first.

## Direct-from-Ove and widgets

1. Seat → LEAD, priority false, plan only. Stop.
2. LEAD polls the held message and answers with a plan.
3. Seat edits, then posts the Desk result labeled `awaiting-review / pending QUALITY`, and sends the receipt priority false.
4. For a true widget: seat asks LEAD priority false → LEAD shows it to Ove 1:1 → LEAD posts the selection into the Desk and SendToAgent the seat priority true → seat continues.

