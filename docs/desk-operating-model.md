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
which is enabled on all seven seat templates. Eight points are desk policy rather than skill detail:

1. **No repo work before a brief that succeeded, and success is judged in two steps.** Reading files
   is fine; editing, committing, branching, pushing, opening a PR, or any `write` tool call waits for
   the brief. A seat that edits first is re-deciding something already recorded in the memory plane it
   skipped. A failed brief arrives in **one of two shapes** and the check that catches one is blind to
   the other, so classify before judging. **Shape A — the call never ran:** the gateway hands back a
   sparse object with a **top-level `error` and a top-level `reason`** (`unknown_tool`, `deadline`,
   `forbidden`, `invalid_args`, `secret_refused`, `backend_missing`, `internal`) and no `substrate` or
   `recall` field to inspect. **Shape B — the call ran and buried the failure.** **A populated response
   is not a successful brief**: `desk_brief` returns its full shape even when the substrate is
   unreachable, sets no top-level `reason` there, and the failure sits in `substrate.error`, in
   `recall.error`, **or per bank in `recall.results[].error`** — with Hindsight configured the gateway
   loops the banks and returns early, so `recall.error` is never set and a dead bank is only visible
   inside `results[]`. The top-level `error` key is the discriminator, and **one failed bank is enough**:
   losing `pd-desk` means the brief cannot tell the seat what the desk already decided. A seat that
   checks only the envelope, or only `recall.error`, reads an outage as a quiet ticket; a seat that goes
   straight to `substrate.error` reads `undefined` for a brief that was never run.
2. **Record what you read, and claim no more than the tool supports.** Where a tool's contract carries
   an etag, the receipt records `brief_etag` and change detection is real. `desk_brief` carries none,
   so the receipt records `brief_read_at` (its `generated_at`) **and** `cached`, and the seat states in
   `unverified` that it could not tell whether the brief changed under it. `generated_at` is a read
   timestamp, not a revision id: it moves on every fresh call whether or not memory changed, and a
   cache hit carries the original assembly time for up to five minutes after memory changed — so it is
   never recorded as `brief_etag` and never diffed. `cached` is added only on a cache hit and the fresh
   path never sets the key, so **an absent `cached` means `false`** — not an incomplete brief, and not a
   value to record as though the response carried it. **Absence of an etag field is not an upstream
   failure** — reporting it as one describes an outage that did not happen — **but it is not a licence
   to edit either**: see point 3.
3. **Degraded mode needs a human ack, and there are two conditions.** The first is the brief *failing*
   per point 1, in either shape — blocker code `brief_degraded`. The second is a brief that **succeeded
   and carries no revision marker**, which is every `desk_brief` seat today because the roster exposes
   no etag — blocker code `brief_no_revision_marker`. Both are *unknown*, never *none*, and in both the
   repo work needs a recorded acknowledgement with the `operation` string for its condition
   (`degraded-loop: repo work without a memory brief`, or `…on a brief with no revision marker`). A read
   timestamp is not a substitute for the marker: **no seat proceeds to an edit on `generated_at` and
   `cached` alone.** Acks route the way approvals already do: a build seat asks LEAD priority false;
   LEAD asks Ove in the 1:1. The ack id goes in the receipt's **`loop_acks`, never in `approvals[]`** —
   `approvals[]` is G-5/G-6's destructive-operation surface, where the gate validates every entry and
   pairs entries to destructive commands by count, so a turn ack there either fails a receipt whose
   destructive op was properly approved or silently satisfies G-6 for one that was not. The verbatim
   reason plus
   its field path go in `unverified` — the **top-level `reason`, with its `error` code**, for Shape A, and
   `substrate.reason`, `recall.reason` or `recall.results[<bank>].reason` **named with its bank** for a
   per-bank Hindsight failure, since `pd-desk` and `pd-<seat>` failing are different incidents. An ack
   covers one turn on one ticket, it is not a g5/g6 `approval_id`, and it is never typed by the seat
   that needs it. No ack is a blocker, and a reported blocker is a finished turn. The second condition
   retires when QUALITY lands the etag (G-4); until then the ack volume is the cost of the gap, and the
   silent alternative is the defect.
4. **Degradation is signalled in the event payload, never by swapping the event kind** — and with one
   payload field per meaning. A degraded turn that got its ack and finished the work still emits
   `implementation.completed` with the receipt path, plus `payload.degraded: true`, `payload.blocker`
   (the desk code), `payload.upstream_reason` (the verbatim string, where there is one),
   `payload.reason_path` (the field it came from) and the ack id. A single `payload.reason` cannot hold
   the code and the diagnostic at once, so it holds neither reliably. `ticket.blocked` is for the turn
   that *stopped* — no ack, or ack refused — and a finished turn labelled `ticket.blocked` sends LEAD
   chasing a blocker for work that is sitting ready for review.
5. **The gateway does not preserve the catalogue kind, and the desk records that as a gap.**
   `desk_event_emit` writes every event with top-level `kind: "note"` and puts the kind it was given in
   `payload.event` (plus the `summary` string), so on the gateway path **`payload.event` is the routing
   field and the top-level `kind` carries no type at all**. Seats still pass the catalogue kind — it is
   what lands there — and never claim an emission routed to a consumer. The gateway also injects
   `seat`, `event` and `task_id` into every payload and merges the seat's keys over them, so a payload
   must not set those three. Closing the gap is QUALITY's contract change (G-4): either a `kind`
   passthrough, or `docs/handoff-contracts.md` stating that the gateway path routes on `payload.event`.
6. **A memory write is not atomic, and `ok: true` is not proof.** `desk_memory_retain` writes to
   Hindsight and to the substrate and reports each in `results`, but returns `ok` if **either** plane
   accepted — so `ok: true` can mean the fact is in one plane and missing from the other. Seats read
   `results` per plane and record a partial write in `unverified` rather than claiming "retained". An
   error is not proof nothing was written either: only the local refusals (`evidence_required`,
   `secret_refused`) return before any upstream call, while a timeout can follow an upstream commit.
   The roster accepts no idempotency key, so an uncertain outcome is recalled before it is retried, at
   most once, and a possible duplicate is stated.
7. **Docs and memory only through the substrate or the gateway.** No seat default calls a raw
   RAGFlow or Hindsight server (`user-ragflow`, `user-hindsight`, or a direct MCP/HTTP endpoint):
   that path needs a credential the seat must not hold, leaves no event row, and can retain outside
   `pd-<seat>`.
8. **Skills are listed and invoked only.** A seat does not install, enable, edit, publish or approve
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
4. **Implement** — Specialist runs the production loop above: a brief that succeeded on all of its nested error fields (including per-bank `recall.results[]`) before the first edit, plus a revision marker or a recorded degraded-mode ack, then executes only assigned work in owned paths, and writes a receipt.
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
  - Production loop run: brief before the first edit with a revision marker or a recorded degraded-mode ack, `memory_write` and `events_emit` in the same turn, per-plane retain outcome recorded
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

**An approval must be bound to a sha, and must not create one.** Neither property holds today, and
the two reasons are different in kind:

- `desk_receipt_approve` gates the receipt before it stamps, and `ci/gates/check_receipt.py` treats
  an absent `approved_by` as a failure — so on an unstamped receipt, the expected input, the
  preflight refuses and the stamp is never reached. Beside it in the same function, the tool reads
  the receipt at one sha and commits it from a fresh clone taken later with no comparison between,
  so a concurrent push is silently overwritten. Both are specified for `bot-01-systems-backend` as
  companions C-1 and C-2 in
  [`../skills/desk-bootstrap/desk-production-loop/companion-patches/`](../skills/desk-bootstrap/desk-production-loop/companion-patches/README.md).
  **Once they land**, a stamp on an unstamped receipt succeeds, the gates run over exactly the bytes
  committed, and a raced stamp fails loudly instead of clobbering.
- What the companions do **not** fix: writing the approval into a file on the PR branch **creates a
  new tip**. Greptile's COMPLETED and the reviewed sha both name the old one, and the merge head
  becomes a commit nothing reviewed. **Advancing the tip is not a side effect of the stamp; it is
  the stamp** — an approval delivered as a commit cannot describe the head it is committed to.

So the approval does not live in the receipt file. The receipt carries an `approval_ref` —
`kind` (`check_run`, `pr_review` or `gateway_store`), `name`, and the `reviewed_sha` the reviewer
actually read — and G-2 resolves it against the **current head** at gate time, passing only when an
approval exists for that exact sha. Preferred mechanism is a GitHub check run on the reviewed sha
(`POST /repos/{repo}/check-runs` takes `head_sha` as a required field, so the binding is structural,
and the gateway already holds a GitHub token); a PR review approval and a gateway-store record keyed
by `(receipt_path, reviewed_sha)` are the fallbacks, the latter following the no-commit precedent
`contract_ack` already sets with `store.record_ack`.

Every part of this is foreign to LEAD — `services/**` is bot-01's, `ci/gates/**`,
`skills/verification-receipts/**` and `contracts/tool-rosters/**` are bot-06's — so a LEAD PR ships
the specification and not the code. Until the companions land, an approval that leaves the reviewed
tip intact is not obtainable, and no seat writes a placeholder into `approved_by` to work around it:
an empty string fails the same check, and a filled-in one fabricates the independent review the gate
exists to require.

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

