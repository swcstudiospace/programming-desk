---
name: desk-production-loop
description: The default production turn for a desk seat — memory_brief (+ its etag or revision marker) before any repo work, act inside owned paths, memory_write, events_emit, handoff_to_hermes. Use at the start of every ticket, before the first edit, and before any completion claim. Also use to decide whether a failed brief permits degraded mode, and which event kind a degraded turn emits.
bots: [all]
gates: [G-1, G-2, G-3]
---

# Desk Production Loop

**Owner:** Programming Lead (bot-00) per `ownership.yaml`. LEAD owns the loop as desk policy; it
does not own the product code a seat writes while running it.

**Path note:** this skill lives under `skills/desk-bootstrap/` because `skills/**` defaults to
QUALITY and `skills/desk-bootstrap/**` is LEAD's carve-out. The intended home is
`skills/desk-production-loop/`, which needs one last-match rule in `ownership.yaml` from QUALITY
(the same carve-out shape as `skills/agent-bus/**`). Until that rule exists, LEAD editing a new
top-level skill directory is a G-1 FOREIGN failure, and inventing the ownership line is the thing
LEAD has already been told twice not to do.

## When this applies (L1)

You are a bootstrapped desk seat (`skills/desk-bootstrap` finished, `desk_doctor check` green) and
you have a ticket. This is the turn shape for every ticket, not an optional enhancement:

```
brief ──▶ act ──▶ memory_write ──▶ events_emit ──▶ handoff_to_hermes
```

**The one hard precondition: no repository work before a brief that succeeded — judged on the
nested error fields (§2.1), with what you read recorded in the receipt (§2.2).** Reading
files is fine. Editing, committing, branching, pushing, opening a PR, or calling any `write` tool
is repo work, and all of it waits for the brief. A seat that edits first is deciding again
something the desk already decided, with no way to know it — and the memory plane it was supposed
to consult is the only place that record lives.

```
Ticket in hand. About to touch the repo?
│
├─ memory_brief called this turn?              NO ──▶ Call it. §2
│  │ YES
├─ Did it succeed?  Check the NESTED error     NO ──▶ DEGRADED. Human ack or stop. §3
│  │  fields, not the top level — §2.1.                (a populated response is not a
│  │  desk_brief: substrate.error absent AND            successful one)
│  │  recall.error absent AND tool was
│  │  listed AND not deadline-cut.
│  │ YES
├─ Recorded what you read in the receipt?      NO ──▶ Record it, then act. §2.2
│  │ brief_etag where the tool has an etag;           (a successful brief from a tool with no
│  │ otherwise brief_read_at + cached.                 etag field is NOT degraded — §2.2)
│  │ YES
├─ Paths resolve to your seat?                 NO ──▶ Not yours. Blocker to LEAD (G-1). §4
│  │ YES
├─ Need docs or memory?  ──▶ substrate/gateway only. Never a raw docs or memory server. §4
├─ Need a skill?         ──▶ list and invoke. Never install, edit or approve one. §4
│  │
└─ Act ──▶ memory_write (§5) ──▶ events_emit (§6) ──▶ handoff_to_hermes only if the ticket
            hands off (§7). Receipt before the claim, every time (G-2).
```

Three rules hold at every phase: the seat holds no credentials and types none into an argument
(G-3, PD-4); a tool the connector did not list does not exist; a `read` that failed open returned
*unknown*, never *none*.

---

## Method (L2)

### §1 The five phases and the tools that serve them

The loop is defined by the substrate tools reached through the Hermes connector. Each has a
gateway `desk_*` equivalent on the seat endpoint, and the two are the same plane — the gateway
calls the substrate. Use whichever your `tools/list` actually shows.

| Phase | Substrate / connector tool | Gateway equivalent | Kind |
|---|---|---|---|
| 1 · brief | `memory_brief` | `desk_brief` | read (fails open) |
| 2 · act | `graph_get`, `memory_search`, plus your seat's own tools | `desk_docs_search`, `desk_memory_recall`, `desk_ownership_resolve` | read |
| 3 · memory_write | `memory_write` | `desk_memory_retain` | write (fails closed) |
| 4 · events_emit | `events_emit` | `desk_event_emit` | write (fails closed) |
| 5 · handoff | `handoff_to_hermes` | — (LEAD only; `desk_bus_start_job` is the Lane B path) | write |

Phases 3 and 4 are not reporting. They are how the next turn — yours or another seat's — learns
that this turn happened at all. A turn that edits code and emits nothing is invisible to the brief
that the next seat will read, which is exactly the state §2 exists to prevent.

### §2 Phase 1 — brief

Call `memory_brief` (or `desk_brief`) once at the start of the turn, with `graph_id` and `task_id`
when the ticket carries them. What comes back is the substrate brief for the graph, recall from
`pd-<seat>` and `pd-desk`, and the seat's open tickets.

Two separate questions follow, and conflating them is how this section has gone wrong before:
**did the brief succeed** (§2.1), and **what do you record about what you read** (§2.2).

#### §2.1 Did it succeed? Read the nested error fields

**A populated response is not a successful brief.** `desk_brief` always returns a populated object —
`seat`, `generated_at`, `substrate`, `recall`, `loaded_packs`, `intake_queue`, `reminders`, and
`cached` on a cache hit. **There is no top-level `reason`. Do not look for one.** When the substrate
is unreachable or unconfigured, the gateway still hands back that shape and buries the failure one
level down.

`desk_brief` succeeded only if **all** of these hold:

| Check | Where it comes from |
|---|---|
| `substrate.error` is absent | `core.brief` caches the result only `if not substrate.get("error")` — that is the gateway's own test for whether the brief was real. `upstreams.SubstrateClient.brief` returns `{error: UPSTREAM_ERROR, reason: …}` on an HTTP error or a ≥400, and `not_configured("substrate")` when no credential is set |
| `recall.error` is absent | `core.memory_recall` sets `error` and `reason` on the recall object when the memory plane is unreachable. Recall dead means prior decisions are invisible, which is the condition §3 exists for even when the substrate brief itself is fine |
| The tool was listed, and the call was not cut by the 20 s deadline | `skills/desk-gateway` §1, §4 |

Anything else is §3, however full the top level looks. A seat that checks only for a top-level
`reason` will read a substrate outage as a quiet ticket and edit without an ack — the precise hole
this section is here to close.

For a substrate `memory_brief` reached through the connector, apply the same discipline to whatever
its live response uses: find the field that says the upstream failed, and do not accept the envelope
as the answer.

#### §2.2 What to record — and what it does not prove

Record it in the receipt alongside the `task_id`, and on the writes of this turn wherever the live
schema accepts it, so `memory_write` and `events_emit` are attributable to the state you read.

| Brief you called | Record | Supports change detection? |
|---|---|---|
| A tool whose contract carries an etag, and it returned one | `brief_etag: "<etag>"` | **Yes** — re-brief with `refresh: true`, and if the etag moved, re-read before you claim anything |
| `desk_brief` today | `brief_read_at: "<generated_at>"` **and** `cached: <true\|false>` | **No** — see below |
| A tool whose contract carries an etag and it came back without one | nothing — that brief did not complete. §3 | — |

**`generated_at` is a read timestamp, not a revision id, and it cannot be compared.** It is the wall
clock when the gateway assembled the response, so it moves on every fresh call whether or not memory
changed, and on a cache hit the response carries the *original* assembly time for up to five minutes
after memory has changed. Recording it as `brief_etag` and diffing it would produce a false alarm on
every fresh call and silence in exactly the window where a change is most likely — which is why it
goes in `brief_read_at` under its own name, never in `brief_etag`.

What it is still good for: it bounds the staleness of the read, and with `cached` it lets a reviewer
place the read in time against the rest of the receipt. Record both or neither — a bare timestamp
from a cache hit reads as fresher than it is.

**So, with no etag, change detection is not available to you.** Do not pretend otherwise. Instead:
before a claim that depends on memory state, re-brief with `refresh: true` to get past the cache, and
note in `unverified` that you could not detect whether the brief changed under you. The `refresh`
call is what you have; comparison is what you do not. Once QUALITY lands the etag in `_core.yaml`
(G-4), row 1 applies to `desk_brief`, row 2 retires, and comparison becomes real.

Re-brief with `refresh: true` when the turn spans a long gap, after your own `memory_write` if you
need the fact back in the same turn, or when another seat may have written to `pd-desk` meanwhile.

#### §2.3 The etag is not in the roster yet

`contracts/tool-rosters/_core.yaml` gives `desk_brief` no etag output, and `desk_memory_retain` and
`desk_event_emit` take no etag input. Every roster schema is `additionalProperties: false`, so
passing one today is a validation error rather than an ignored hint — the receipt is where the read
is recorded until QUALITY lands that change (G-4).

**A successful brief from a tool whose contract has no etag field is not degraded.** The opposite
reading would put every gateway-backed turn on the desk into §3 and make a human ack the price of
ordinary work, which is the failure mode §3 exists to avoid, not to create. Absence of an etag field
is a limit on what you can *prove about staleness* (§2.2), never evidence that the brief failed —
that question is settled by §2.1 and by nothing else.

### §3 Degraded mode needs a human ack

`memory_brief` is a `read`, so it fails **open**: an upstream failure is reported inside the response
rather than raised. For `desk_brief` the response stays fully populated and the failure sits in
`substrate.error` or `recall.error` (§2.1) — which is the dangerous case, because a brief that failed
looks, at the top level, exactly like a ticket nobody has touched.

**Degraded mode is the brief failing, per §2.1** — `substrate.error` present, `recall.error` present,
the tool not listed, the call cut by the 20 s deadline, or an etag-bearing tool returning no etag. It
is **not** a successful brief from a tool that has no etag field (§2.3), and it is **not** a cache hit.
Neither of those is a failure, and treating them as one makes an ack the price of every ordinary turn.

In degraded mode you may read the repository and you may report. You may **not** do repo work
without a recorded human acknowledgement:

| Step | What it is |
|---|---|
| 1 | Stop before the first edit. Do not retry in a loop — one retry, then it is degraded. |
| 2 | Ask for the ack the way approvals are already routed: a build seat asks LEAD (priority false); LEAD asks Ove in the 1:1. State the tool, the verbatim nested `reason` (`substrate.reason` or `recall.reason`) and which field carried it, and what you intend to edit. |
| 3 | Record the returned ack id in the receipt under `approvals`, with `operation: "degraded-loop: repo work without a memory brief"`, and put the verbatim `reason` plus its field path in `unverified`. |
| 4 | Act, and emit the **normal** kinds for what happened — `implementation.started`, then `implementation.completed` with the receipt path — each carrying `payload.degraded: true`, `payload.reason` and the ack id. Degradation is a property of the turn, not its outcome (§6). |
| 5 | Do **not** fire `handoff_to_hermes`. A handoff propagates an unknown memory state into another runtime, where it stops being visible. Hand off only if the ack says so in as many words. |

If the ack does not come, or is refused, the turn stops and **that** is the `ticket.blocked` case:
emit it with `payload.reason: "brief_degraded"` and the verbatim brief `reason`. Its consumer is LEAD,
which is correct for a turn that produced nothing and needs a decision.

An ack authorises **one turn** of repo work on **one ticket**. It is not an `approval_id` for a g5
or g6 tool and does not substitute for one. **Never type an ack id you were not given** — a
plausible string satisfies a receipt field and puts a fabricated approval in the audit trail, which
is a PD-5 breach with evidence attached (`skills/desk-gateway` §3).

No ack, or no answer yet: that is a blocker, and a blocker reported is a finished turn. Report the
reason and stop. It is not a licence to work and retro-fit the ack afterwards.

### §4 Phase 2 — act, and the three things act never does

Act on the ticket, in your own paths, with the evidence discipline the pack already sets:
`desk_ownership_resolve` (or `ownership.yaml` at `origin/main`) before the first edit; one owner per
path; cross-seat work through `docs/cross-bot-protocol.md`, never a direct edit (G-1).

**Docs and memory go through the substrate or the gateway. Never a raw docs or memory server.**

| You want | Use | Never |
|---|---|---|
| A document or a chunk | `desk_docs_search` (gateway) / the substrate docs plane | A RAGFlow MCP server added as a seat connector, a `user-ragflow`-shaped tool, or raw HTTP to a RAGFlow host |
| A remembered fact | `memory_search` / `desk_memory_recall` | A Hindsight MCP server added as a seat connector, a `user-hindsight`-shaped tool, or raw HTTP to a Hindsight host |
| To keep a fact | `memory_write` / `desk_memory_retain` (§5) | Any write that reaches Hindsight without passing the redactor |

The reason is not tidiness. The substrate holds the tenant key and runs the D-04 redactor; the
gateway derives your bank from your seat token. A raw call inverts both: the seat needs a
credential it should not hold, the read or write never reaches the event log, and a retain can land
outside `pd-<seat>` where no reviewer will look for it. **No desk seat template lists a raw docs or
memory connector**, and adding one is a seat-default change, which is a pack PR — not something a
seat does to itself mid-turn.

> This repository's `.mcp.json` does configure `hindsight` and `ragflow` HTTP MCP servers. That
> file is INFRA's (`ownership.yaml`, `.mcp.json` → bot-05) and it is Lane A *cloud-session* tooling,
> not a desk seat default. A seat running inside such a session still routes memory and docs
> through the substrate or gateway path above, so the desk's writes stay redacted, banked and
> audited. Re-scoping or removing those entries is an INFRA ticket.

**Skills: list and invoke only.** You may list the skills you hold and invoke them. You may not
install, enable, disable, edit, publish or approve one — for yourself or for another seat. The
substrate's `skills_propose` opens a PR against `swcstudiospace/agent-skills`; a proposal is not an
installed skill. **There is no `skills.approve` capability yet**, so until one exists — a recorded
human approval on a skill change — the only route into a seat's default set is a reviewed PR to this
repository, `scripts/generate-templates.py`, and `skills/pack-sync` in the one direction it runs.
A seat that adds a skill to itself is executing unreviewed instructions with no receipt, and
`desk_doctor check`'s `installed_skills` row will disagree with the pack on the next run.

> **Doctor does not yet require this skill.** `_declared_skills()` in
> `services/desk-gateway/src/desk_gateway/tools/core.py` builds the required list from the
> `<skill path="…">` entries in `prompts/<bot_id>.xml` plus a hard-coded
> `("verification-receipts", "desk-doctor", "desk-bootstrap")`. `desk-production-loop` is in neither,
> so a seat that never installed it still gets a green skills row. Adding it to that tuple is a
> one-line SYSTEMS change on a path LEAD does not own. Until it lands, a green doctor row is
> **silent** about this skill — compare your `/` menu against your `grokbot/templates/<SEAT>.md`
> instead, and tell LEAD if it is missing.

**Write the receipt before the claim**, per `skills/verification-receipts` (G-2). The loop does not
replace that; phases 3 and 4 are downstream of it, because `memory_write` is refused without a
`receipt_path` or a `source`.

### §5 Phase 3 — memory_write

One fact per call, with its evidence, per `skills/hindsight-memory` §3. The loop adds only this:
**the write happens in the same turn as the work**, not "later". A turn that ends without it leaves
the next brief describing a desk where this turn did not happen.

`memory_write` is a `write`: it fails **closed**. An error means nothing was retained — do not
assume a partial effect, and retry once only if the `reason` is transient. If it stays refused,
that is a blocker and the receipt is still the durable record.

Nothing goes in `content` that you would not publish: the redactor is a backstop, and the audit row
outlives it (G-3, PD-4).

### §6 Phase 4 — events_emit

Emit the turn onto the event log so the desk can see it without reading your chat. Use the kinds
already in `docs/handoff-contracts.md` — `implementation.started`, `implementation.completed`,
`review.requested`, `ticket.blocked` — and pass `graph_id` and `task_id` so the row ties to the
ticket.

**Do not mint a new event kind.** The catalogue is QUALITY's (`docs/handoff-contracts.md`); a kind
no consumer reads is a row nobody will ever act on. A dedicated `loop.*` kind would be a welcome
contract change, and it is QUALITY's to make (G-4).

**A degraded turn (§3) is signalled in the payload, never by swapping the kind.** The kind says what
happened to the work; `payload.degraded` says what the seat knew while doing it. The catalogue routes
on kind, so swapping it misroutes the turn:

| The turn | Kind | Payload |
|---|---|---|
| Completed, brief fine | `implementation.completed` | `receipt_path` |
| Completed, brief degraded, ack recorded | `implementation.completed` | `receipt_path`, `degraded: true`, `reason`, ack id |
| Stopped — no ack, or ack refused | `ticket.blocked` | `reason: "brief_degraded"`, the verbatim brief `reason` |

`implementation.completed` is what carries finished work and its receipt to the integrator and
QUALITY; `ticket.blocked` is a blocker escalated to LEAD. Labelling a finished degraded turn
`ticket.blocked` would report a blocker for work that is actually sitting ready for review — the
receipt would say one thing and the event log another, and the seat waiting on LEAD would be waiting
for nothing.

Payloads are redacted and capped at 4 KB. Put identifiers and outcomes in them, not transcripts.

### §7 Phase 5 — handoff_to_hermes, and the signed-packet stub

Fire a handoff only when the ticket hands off — a durable Hermes EXECUTE that this seat is not the
one to run. It is not the end-of-turn ritual; most seat turns end at §6 with a receipt and a Desk
post labelled `awaiting-review / pending QUALITY`.

**Live shape today** (`docs/vps-agent-bus.md` §2): required `goal` (string) and `messages` (array of
free-form objects). Optional `title`, `priority` (default `normal`), `labels`, `tenant_id`,
`idempotency_key`. The older design-intent shape — `repo`, `branch`, `graph_id`,
`work_packet_markdown`, `prompt` as separate arguments — is **not** live; fold those into `goal` and
`messages`. One handoff per goal; poll `get_task`; never hand off a goal that already has an Agent
Bus job (`skills/agent-bus`), because two runtimes on one goal produce two branches and a merge
race.

**Signed packet — stub only, pending SPE-4792.** The handoff is expected to carry a signed packet so
a receiving runtime can verify the desk actually issued it. That schema is SPE-4792's and has not
landed. Until it does:

| Reserved field | What it will hold | What you do today |
|---|---|---|
| `packet_version` | Schema version of the signed packet | Omit |
| `packet_payload_sha256` | Digest of the canonical packet the signature covers | Omit |
| `packet_signed_at` | Signing timestamp | Omit |
| `packet_key_id` | **Identifier** of the desk signing key — a reference, never key material | Omit |
| `packet_signature` | Detached signature over the digest | Omit |

Rules that already bind, before the schema exists:

- **Omit them.** These names are provisional; when SPE-4792 lands, its schema wins and this table
  is the thing to fix. Sending a provisional field into a `additionalProperties: false` schema is a
  validation error, and sending it into a permissive one is a field the receiver will mis-read.
- **Never invent a value.** Not a signature, not a digest you did not compute, not a `packet_key_id`.
  The desk holds no signing key on the seat and never will: signing belongs to the gateway or the
  substrate, which is where the key lives. A fabricated signature is worse than an absent one — it
  asserts provenance that nothing checked (G-3, PD-4).
- **Say the handoff is unsigned.** Put `handoff_to_hermes packet is unsigned — SPE-4792 signed-packet
  schema not landed` in the receipt's `unverified`. A reviewer must not have to infer it.
- **`goal` still carries the whole work packet** in the meantime, and the same text goes in the draft
  PR body. A paraphrased `goal` means the runtime implements something the PR cannot be reviewed
  against — the signature would not have fixed that.

### §8 What the loop never does

| Never | Because |
|---|---|
| Edit before a brief that succeeded, without a recorded ack | §2, §3 — the decision may already exist and you cannot see it |
| Treat a successful brief as degraded because the tool has no etag field | §2.3 — that reading makes a human ack the price of every ordinary turn |
| Read the envelope as the answer — top-level fields present, so "it worked" | §2.1 — `desk_brief` returns a full object on failure; the verdict is `substrate.error` / `recall.error` |
| Record `generated_at` as `brief_etag`, or diff it | §2.2 — it is a read timestamp; it moves on every fresh call and freezes for five minutes on a cache hit |
| Retry a failed brief in a loop | One retry, then degraded. The audit log fills with the same refusal |
| Treat an empty brief as "nothing known" | It fails open. Empty plus a `reason` is *unknown* |
| Call a raw docs or memory server | §4 — un-audited, needs a credential the seat must not hold |
| Install, edit or approve a skill for itself | §4 — unreviewed instructions, no receipt, no `skills.approve` |
| Edit a foreign path to "finish the feature" | G-1. Cross-seat work is contract-first |
| Mint an event kind | §6 — nothing consumes it |
| Swap a kind to signal degradation | §6 — the catalogue routes on kind; a finished turn labelled `ticket.blocked` reports a blocker for work that is ready for review |
| Invent an ack id, an `approval_id`, or a packet signature | PD-5, G-3 — a fabricated approval with an audit trail |
| Claim done without a receipt | G-2. A claim without a command is a guess with confident phrasing |
| Hand off a goal that already has an Agent Bus job | Two branches, one goal, a merge race a human untangles |

---

## Worked examples

**Good — SYSTEMS, one ticket, gateway brief (the common case today).**

```
desk_brief {graph_id: "ut-…", task_id: "intake-ack-idempotent"}
  → {seat, generated_at: 1790761742.31, cached: false,
     substrate: {ok: true, brief: "…"},          ← no .error  ✔ §2.1
     recall: {banks: ["pd-systems","pd-desk"], results: [ … ]},   ← no .error  ✔ §2.1
     loaded_packs, intake_queue, reminders}
    Brief SUCCEEDED. recall shows a 2026-09-24 decision on the ack path.
receipt stub: task_id, brief_read_at: 1790761742.31, cached: false   ← §2.2 row 2, NOT brief_etag
desk_ownership_resolve {paths: ["services/desk-gateway/src/…/intake.py"]}  → bot-01  ✔ mine
desk_event_emit {kind: "implementation.started", graph_id, task_id}
… edit, run the tests, record cmd + exit_code in the receipt …
desk_memory_retain {content: "Intake ack replays are collapsed on idempotency_key in the gateway,
  not the queue; window is 30 days", receipt_path: ".receipts/bot-01-systems-backend/…json",
  graph_id, task_id, tags: ["intake","idempotency"]}
desk_event_emit {kind: "implementation.completed", graph_id, task_id, payload: {receipt_path: "…"}}
unverified: ["desk_brief exposes no etag, so it is unknown whether the brief changed during the turn"]
Desk post: "awaiting-review / pending QUALITY" + receipt path.  No handoff — SYSTEMS did the work.
```

The seat read the two nested error fields, not the envelope, so a real success was treated as one and
no ack was asked for. `brief_read_at` says *when* it read, with `cached` so the timestamp cannot be
misread as fresher than it is — and the `unverified` line is honest that *whether* memory moved is not
knowable from this tool.

**Good — same seat, brief failed, ack recorded, work finished.**

```
desk_brief {…} → {seat, generated_at: 1790762100.04, cached: false,
     substrate: {error: "upstream_error", reason: "substrate returned HTTP 502"},   ← FAILED
     recall: {banks: [...], results: [], error: "upstream_error", reason: "…"},
     loaded_packs, intake_queue, reminders}
  A fully populated response. Top level looks fine; substrate.error is what decides.  ← §2.1
  One retry, still 502 → DEGRADED.
→ LEAD (priority false): "desk_brief degraded: substrate.error=upstream_error,
   substrate.reason='substrate returned HTTP 502'. Intending to edit
   services/desk-gateway/src/…/intake.py. Ack to proceed?"   → LEAD ↔ Ove → ack-2026-09-30-004
receipt: approvals[{operation: "degraded-loop: repo work without a memory brief",
  approved_by: "…", id: "ack-2026-09-30-004"}];
  unverified: ["substrate.reason 'substrate returned HTTP 502'; recall.error also set; prior
  decisions on this ticket unknown"]; brief_etag: null, brief_read_at: null
desk_event_emit {kind: "implementation.started", …, payload: {degraded: true,
  reason: "substrate returned HTTP 502", ack: "ack-2026-09-30-004"}}
… work, tests, receipt …
desk_event_emit {kind: "implementation.completed", …, payload: {receipt_path: "…",
  degraded: true, ack: "ack-2026-09-30-004"}}     ← completed, NOT ticket.blocked (§6)
No handoff_to_hermes — the ack did not cover one.
```

The work is finished and routes to the integrator and QUALITY as finished work. `payload.degraded`
tells a later reader the seat was flying without the brief. Had the ack never come, the turn would
have stopped and emitted `ticket.blocked` instead — and produced no diff.

**Bad — same ticket, the envelope read as the answer.**

```
desk_brief {…} → populated response; substrate: {error: "upstream_error", reason: "…HTTP 502"}
Seat sees seat/generated_at/recall/reminders all present and no top-level `reason`, calls the
  brief successful, records brief_read_at, edits the ack path, retains "intake acks are not
  idempotent" with the receipt path, and reports done.
```

This is the failure §2.1 exists for, and it survives every check that looks only at the top level. The
brief was *unknown*, not empty — nothing was ever empty. Repo work went ahead with no ack. The
retained "fact" contradicts a decision already in `pd-desk` and carries a receipt path, so it looks
evidenced. The next seat's brief contains both, and the weekly reflect resolves towards the newest —
the wrong one. The correct turn: check `substrate.error`, one retry, then ask LEAD for the ack with
the nested reason quoted, and stop until it arrives.

**Bad — LEAD hands off with a signature it made up.**

```
handoff_to_hermes {goal: "<work packet>", messages: [...],
  packet_signature: "desk-sig-v1-4794", packet_key_id: "desk-lead-2026"}
```

Both values were typed, not computed — no key exists on the seat and SPE-4792 has not landed. The
handoff either fails schema validation or, worse, succeeds and tells the receiving runtime the desk
vouched for a packet nothing signed. Correct: omit the fields, and put the unsigned handoff in
`unverified` (§7).

---

## Failure modes

| Mode | Symptom | Fix |
|---|---|---|
| Edit before the brief | Receipt records no brief at all; work contradicts a recorded decision | Brief first. It is the precondition, not a courtesy |
| Failed brief read as successful | Populated response, no top-level `reason`, so no ack was sought | §2.1 — `substrate.error` and `recall.error` decide, nothing else |
| Empty brief read as "none" | Confident claim about an untouched ticket that was not untouched | Check `reason`; degraded mode (§3) |
| Degraded work, no ack | No `approvals` entry; `unverified` silent on the brief | Get the ack before the edit; an ack cannot be back-dated |
| Fabricated ack id | Receipt field satisfied, audit row matches no approval | PD-5 breach. Obtain a real one |
| Nothing recorded about the brief | Reviewer cannot tell what state you read | `brief_etag`, or `brief_read_at` + `cached`, naming the field it came from (§2.2) |
| `generated_at` recorded as `brief_etag` | A staleness guarantee that does not exist; diffing it alarms on every fresh call and stays silent across a cache hit | §2.2 — it goes in `brief_read_at`; change detection is unavailable until the etag lands |
| Etag moved mid-turn (etag-bearing tool) | Two turns' claims disagree | Re-brief and re-read before claiming |
| Successful brief called degraded because the tool exposes no etag | An ack requested for every ordinary turn; acks stop meaning anything | §2.3 — degraded is the brief *failing*, per §2.1 |
| Cache hit treated as degraded | Same | A cached brief is a brief; record `cached: true` (§2.2) |
| Degraded turn emitted as `ticket.blocked` after finishing the work | LEAD chases a blocker for work sitting ready for review | §6 — kind says the outcome, `payload.degraded` says the conditions |
| Raw docs or memory call | No event row; retain outside `pd-<seat>` | §4 — substrate or gateway only |
| Seat enables its own skill | `installed_skills` disagrees with the pack at next doctor | List and invoke only, until `skills.approve` (§4) |
| Green doctor read as proof this skill is installed | Seat runs without the loop and nothing reports it | `_declared_skills()` in the gateway does not list it yet (§4). Check the `/` menu against the template |
| Turn ends without `memory_write` / `events_emit` | Next brief shows the turn never happened | Both are in-turn, not follow-ups |
| New event kind | Rows nobody consumes | Use the catalogue; ask QUALITY for a kind (G-4) |
| Provisional packet field sent | Validation error, or false provenance | Omit until SPE-4792 lands; say unsigned |
| Handoff on a goal with a bus job | Two branches, one goal | Check receipts and open PRs first (`skills/agent-bus` §2) |

---

## Gate mapping

| Rule | Gate or directive | Why |
|---|---|---|
| A brief that succeeded per §2.1 before repo work, what it returned recorded per §2.2; ack recorded otherwise | G-2, PD-1 | Acting on unknown memory state is claiming without observing |
| Success is judged on the nested error fields, never on the envelope | G-2, PD-1 | A fail-open read returns a full object; the top level cannot tell you it failed |
| No staleness claim the tool cannot support | PD-1, PD-6 | `generated_at` is when you read, not what you read; the gap goes in `unverified` |
| Degradation goes in the payload, never in the event kind | G-4 | The catalogue routes on kind; a misrouted turn is a blocker nobody owns or work nobody reviews |
| `memory_write` refused without `receipt_path` or `source` | G-2 | Memory is downstream of verification, never a substitute |
| Paths resolved to this seat before the first edit | G-1 | One owner per path; an unowned or foreign edit is a silent collision |
| Docs and memory only via substrate or gateway | G-3, PD-4 | The redactor and the tenant key are not the seat's to bypass |
| No fabricated ack id, `approval_id` or packet signature | PD-5, G-3 | A fabricated approval is a breach with an audit trail attached |
| Events use the published catalogue | G-4 | The catalogue is a contract surface with consumers |
| Skills list/invoke only until `skills.approve` | G-2, G-7 | Unreviewed instructions leave no receipt and break the doctor row |
| Receipt before the claim | G-2 | The gate this system exists for |

---

## References

| Path | Role |
|---|---|
| `skills/desk-bootstrap/SKILL.md` | Gets the seat to green. This loop is what it does afterwards |
| `skills/desk-gateway/SKILL.md` | `read` fails open, `write` fails closed, the 20 s deadline, 403, g5/g6 |
| `skills/hindsight-memory/SKILL.md` | Banks, the `receipt_path`-or-`source` rule, redaction |
| `skills/ragflow-docs/SKILL.md` | Docs search finds where; the file is the fact |
| `skills/verification-receipts/SKILL.md` | The G-2 artefact this loop writes every turn |
| `skills/agent-bus/SKILL.md` | Lane B dispatch and the `handoff_to_hermes` fallback |
| `docs/vps-agent-bus.md` | `handoff_to_hermes` live schema; the bus is a computer, not a source of truth |
| `docs/handoff-contracts.md` | Event catalogue and envelope (QUALITY) |
| `docs/desk-operating-model.md` | Where the loop sits in the desk flow |
| `contracts/tool-rosters/_core.yaml` | The eight core tools and their schemas (QUALITY) |
| `ownership.yaml` | `skills/desk-bootstrap/**` → bot-00; `skills/**` → bot-06 |
