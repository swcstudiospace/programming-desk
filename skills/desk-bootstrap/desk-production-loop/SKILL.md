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

**The one hard precondition: no repository work before a brief that succeeded (§2.1) *and* a
revision marker for what it returned (§2.2) — or, failing either, a recorded human acknowledgement
(§3).** Reading files is fine. Editing, committing, branching, pushing, opening a PR, or calling any
`write` tool is repo work, and all of it waits for the brief. A seat that edits first is deciding
again something the desk already decided, with no way to know it — and the memory plane it was
supposed to consult is the only place that record lives.

**On today's gateway the marker does not exist**, so `desk_brief` seats take the ack route for every
turn that edits (§2.3). That is the fail-closed reading of the precondition, not a loophole in it:
`generated_at` and `cached` are a record of when you read, never a substitute for the marker.

```
Ticket in hand. About to touch the repo?
│
├─ memory_brief called this turn?              NO ──▶ Call it. §2
│  │ YES
├─ Top-level `error`?  Shape A — the call       YES ─▶ DEGRADED (brief failed).
│  │  never ran: unknown_tool, deadline,               Quote the TOP-LEVEL reason.
│  │  forbidden, invalid_args … — §2.1.                Human ack or stop. §3
│  │ NO → Shape B, a completed brief
├─ Did it succeed?  Check the NESTED error     NO ──▶ DEGRADED (brief failed).
│  │  fields; there is no top-level reason             Quote the NESTED reason + its path.
│  │  here — §2.1.  substrate.error absent             Human ack or stop. §3
│  │  AND recall.error absent AND no                   (a populated response is not a
│  │  recall.results[].error.                           successful one)
│  │ YES
├─ Revision marker for what you read?          NO ──▶ NOT a failed brief, but the
│  │ brief_etag where the tool has an etag.            precondition is unmet: human ack
│  │ desk_brief has none today, so this                (`no revision marker`) or stop. §2.3, §3
│  │ branch is NO on every gateway seat.               Record brief_read_at + cached either
│  │ YES                                                way — a record, not a licence. §2.2
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

#### §2.1 Did it succeed? Two response shapes, checked in order

A failed brief arrives in **one of two shapes**, and the check that catches one is blind to the
other. Classify the response before you judge it:

**Shape A — the call never ran (call-level failure).** The gateway refused or abandoned the call
before the brief body produced anything, and hands back a **sparse object carrying a top-level
`error` and a top-level `reason`** — no `seat`, no `substrate`, no `recall`. `SeatServer.call_tool`
in `services/desk-gateway/src/desk_gateway/server.py` produces this shape, via
`tools.failure(code, reason)` or its own literals, for `forbidden`, `unknown_tool` (the tool was not
on your roster), `invalid_args`, `secret_refused`, `deadline` (the 20 s cut), `backend_missing` and
`internal`.

**Shape B — the call ran and buried the failure (completed brief).** `core.brief` always returns its
full object — `seat`, `generated_at`, `substrate`, `recall`, `loaded_packs`, `intake_queue`,
`reminders`, plus `cached` on a cache hit — and **sets no top-level `error` and no top-level
`reason` even when the substrate is unreachable or unconfigured**: it buries the failure one level
down. **A populated response is not a successful brief.**

**The discriminator is the top-level `error` key.** Present → Shape A: the top-level `reason` is the
one to quote, and nothing nested exists to check. Absent → Shape B: **there is no top-level
`reason`. Do not look for one**, and the verdict is in the nested fields.

Both shapes are §3. They differ only in *which field the ack, the receipt and the event quote* — see
the reason-path table in §3, which has a row for each.

`desk_brief` succeeded only if **all** of these hold:

| Check | Where it comes from |
|---|---|
| **The response is Shape B at all** — no top-level `error` | A top-level `error` means the call never reached the brief body: `unknown_tool`, `invalid_args`, `secret_refused`, `forbidden`, `deadline`, `backend_missing`, `internal`. Quote the top-level `reason` and stop; there is no `substrate` or `recall` field to inspect |
| `substrate.error` is absent | `core.brief` caches the result only `if not substrate.get("error")` — that is the gateway's own test for whether the brief was real. `upstreams.SubstrateClient.brief` returns `{error: UPSTREAM_ERROR, reason: …}` on an HTTP error or a ≥400, and `not_configured("substrate")` when no credential is set |
| `recall.error` is absent **and** no entry in `recall.results[]` carries an `error` | **Two code paths, two shapes — check both.** With Hindsight configured, `core.memory_recall` loops the banks, appends `{bank, **hit}` per bank and **returns early**, so a failed bank lands in `recall.results[i].error` and `recall.error` is never set. Only on the substrate fallback does it set `recall.error` / `recall.reason`. Recall dead means prior decisions are invisible, which is the §3 condition even when the substrate brief itself is fine |

**One failed bank is enough.** `recall.results[]` has one entry per bank — your own `pd-<seat>` plus
the shared `pd-desk` — and the shared bank is where team-wide standing decisions live. A response
where `pd-<seat>` answered and `pd-desk` returned `{error: upstream_timeout, …}` is a brief that
cannot tell you what the desk already decided, so it is §3, not a partial success to work around.

Anything else is §3, however full the top level looks. A seat that checks only for a top-level
`reason` will read a substrate outage as a quiet ticket and edit without an ack — the precise hole
this section is here to close, and `recall.results[].error` is the second door into the same room.
The inverse mistake is the same size: a seat that goes straight to `substrate.error` on a Shape A
response reads `undefined` for a brief that was never run, and `unknown_tool` — the case where the
seat holds no brief tool at all — is exactly the one that must not pass.

**What this list covers, and what it cannot.** The three rows above are every failure `desk_brief`
can **report**: row 1 covers everything the dispatcher refuses or abandons before the brief body runs,
and inside a completed brief `substrate` and `recall` are its only upstream-backed fields —
`reminders` is static, and `seat`, `generated_at` and `cached` are computed locally. **If a future
gateway change adds another upstream-backed field to the brief, or another call-level refusal code,
this table is what has to grow with it** — a rule written against one code path while the gateway
had two is the mistake this section has made more than once.

`loaded_packs` and `intake_queue` are a different case, and calling the list "complete" would paper
over it. They come from the gateway's local store, whose reader swallows the failure:

```python
def _read(self, name, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default          # ← a corrupt or unreadable store reads as empty
```

So those two fields **cannot fail loudly — they fail silently**, which is worse than failing: an
empty `loaded_packs` or `intake_queue` means *empty or unreadable, indistinguishable*, and every
check in the table still passes.

The consequence is narrow but real. This is **not** degraded mode — the memory plane is not involved,
and §3 is about prior decisions being unknown. But **do not claim either field's emptiness as a
fact**: "no pack is loaded" and "the intake queue is empty" are not things a brief can tell you. A
seat that reports "queue empty" off a brief whose store file was unreadable has invented an
observation, which is PD-1 whether or not a gate catches it.

**There is no second tool that settles it, and looking for one makes things worse.** Every accessor
goes through the same `_read` default, so a "confirming" call returns the same empty answer with no
additional information:

| Tempting | What it actually does |
|---|---|
| `desk_roster_status` to re-check the queue | Returns `"intake_queue": svc.store.intake_counts()` — **the same call the brief made**. Identical empty result, now with false confidence behind it. `packs_for` is the same story for the `packs` and `tool_count` rows |
| A pack load or unload to "see" the pack list | **A write, not a check.** `store.load_pack` does `_read("packs", {})` → mutates → `_write`, so on a corrupt file it reads `{}`, then **overwrites the file**, discarding every seat's pack state. Diagnosing with this destroys the evidence and the data |

So the only honest handling is: **record it in `unverified` as unread, and leave it there.** "Intake
queue reported empty by `desk_brief`; cannot distinguish empty from an unreadable store, not
independently observed" is a complete and correct entry. If the answer actually matters to the
ticket, it is a question about the store file on the gateway host — an INFRA or SYSTEMS ask — not
something a seat can resolve from tool output, and not a reason to start writing to the store.

For a substrate `memory_brief` reached through the connector, apply the same discipline to whatever
its live response uses: find the field that says the upstream failed, and do not accept the envelope
as the answer.

#### §2.2 What to record — and what it does not prove

Record it in the receipt alongside the `task_id`, and on the writes of this turn wherever the live
schema accepts it, so `memory_write` and `events_emit` are attributable to the state you read.

| Brief you called | Record | Supports change detection? | Repo work |
|---|---|---|---|
| A tool whose contract carries an etag, and it returned one | `brief_etag: "<etag>"` | **Yes** — re-brief with `refresh: true`, and if the etag moved, re-read before you claim anything | Go ahead |
| `desk_brief` today | `brief_read_at: "<generated_at>"` **and** `cached: <true\|false>` | **No** — see below | **Needs the §3 ack** — no revision marker |
| A tool whose contract carries an etag and it came back without one | nothing — that brief did not complete. §3 | — | **Needs the §3 ack** — brief failed |

**`cached` is present only on a cache hit.** `core.brief` adds it in the cache branch
(`return {**cached[1], "cached": True}`) and the fresh path never sets the key at all — including
under `refresh: true`. **An absent `cached` means `false`.** Record `cached: false` in that case. Do
not treat the missing key as an incomplete brief (it is not a §2.1 failure — `cached` is computed
locally and has no upstream), and do not record a value the response literally carried when it
carried none: say `cached: false` because the key was absent, not because the gateway returned
`false`.

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

**And `brief_read_at` + `cached` is a record, never a licence.** Recording them satisfies *this*
section — a reviewer can place the read in time — and satisfies nothing else. The loop's precondition
is a brief **and its revision marker** before repo work, so a brief with no marker leaves the
precondition unmet and repo work needs the §3 acknowledgement under the
`no revision marker` operation. **Never proceed to an edit on `generated_at` and `cached` alone.**
That is the silent path this table used to permit, and a timestamp that moves on every call is not
the thing the precondition asked for.

Re-brief with `refresh: true` when the turn spans a long gap, after your own `memory_write` if you
need the fact back in the same turn, or when another seat may have written to `pd-desk` meanwhile.

#### §2.3 The etag is not in the roster yet

`contracts/tool-rosters/_core.yaml` gives `desk_brief` no etag output, and `desk_memory_retain` and
`desk_event_emit` take no etag input. Every roster schema is `additionalProperties: false`, so
passing one today is a validation error rather than an ignored hint — the receipt is where the read
is recorded until QUALITY lands that change (G-4).

**A successful brief from a tool whose contract has no etag field is not a failed brief.** Whether
the brief *failed* is settled by §2.1 and by nothing else: absence of an etag field is a limit on
what you can *prove about staleness* (§2.2), never evidence that the upstream broke. A seat that
reports "brief failed, substrate down" because the schema has no etag output is describing an
outage that did not happen.

**It is also not a licence to work.** These are two different questions and the skill has previously
run them together in both directions. The precondition in *When this applies* is a brief **and its
revision marker**; with no marker it is unmet, so **repo work still needs the §3 ack** — the
`no revision marker` operation, not the `brief failed` one. So, on today's gateway:

| State | Brief failed? | Repo work | Ack operation |
|---|---|---|---|
| Etag-bearing tool returned an etag | No | Go ahead, no ack | — |
| `desk_brief` succeeded per §2.1, no etag in its contract (**every gateway seat today**) | **No** | **Ack required** | `degraded-loop: repo work on a brief with no revision marker` |
| Brief failed per §2.1 (either shape) | **Yes** | **Ack required** | `degraded-loop: repo work without a memory brief` |

**The cost of the middle row is real and it is the intended cost.** Until QUALITY lands the etag
(G-4), every gateway-backed seat that wants to edit needs an ack, which is a lot of acks — and the
alternative that was tried instead, letting `generated_at` and `cached` stand in for the marker, is
how a seat proceeds on memory it cannot tell has moved. An ack for a known gap is cheap; a silent
proceed is the defect. Two things keep the volume honest rather than the rule loose: the ask is
short (§3 step 2 — tool, state, what you intend to edit) because there is no upstream failure to
diagnose, and **one ack covers the turn** on that ticket, not each edit within it. The middle row
retires the day the etag lands, and nothing else about §3 changes when it does.

Fail-closed is the fallback, not a third option: if the ack does not come, the turn stops and reports
(§3) — it does not proceed with a note in `unverified`.

### §3 Degraded mode needs a human ack

`memory_brief` is a `read`, so it fails **open**: an upstream failure is reported inside the response
rather than raised. For `desk_brief` the response stays fully populated and the failure sits in
`substrate.error` or `recall.error` (§2.1) — which is the dangerous case, because a brief that failed
looks, at the top level, exactly like a ticket nobody has touched.

**Two conditions put a turn in degraded mode, and each has its own ack (§2.3):**

| Condition | Blocker code | Ack `operation` |
|---|---|---|
| **The brief failed per §2.1** — either shape: a top-level `error` (Shape A), or `substrate.error`, `recall.error` or any `recall.results[].error` inside a completed brief (Shape B) | `brief_degraded` | `degraded-loop: repo work without a memory brief` |
| **The brief succeeded but carries no revision marker** — no etag in the tool's contract, which is every `desk_brief` seat today (§2.3) | `brief_no_revision_marker` | `degraded-loop: repo work on a brief with no revision marker` |

A cache hit is **neither**: a cached brief is a brief, and it carries a marker exactly as well as a
fresh one does — which today is not at all. Record `cached: true` and take the second row like any
other `desk_brief` turn.

In degraded mode you may read the repository and you may report. You may **not** do repo work
without a recorded human acknowledgement:

| Step | What it is |
|---|---|
| 1 | Stop before the first edit. Do not retry in a loop — one retry, then it is degraded. (Nothing to retry on the no-marker condition: the contract will not grow an etag between two calls.) |
| 2 | Ask for the ack the way approvals are already routed: a build seat asks LEAD (priority false); LEAD asks Ove in the 1:1. State the tool, the condition, the verbatim `reason` **and the path that carried it** where there is one, and what you intend to edit. |
| 3 | Record the returned ack id in the receipt under **`loop_acks`** — **not `approvals`**, see below — with the `operation` string for the condition and **the human who granted it in `human_granted_by`** (the seat that relayed goes in `relayed_by`, which is not the grantor). Put the verbatim `reason` plus its field path, or for the no-marker condition the absence of the marker, in `unverified`. |
| 4 | Act, and emit the **normal** kinds for what happened — `implementation.started`, then `implementation.completed` with the receipt path — each carrying the payload fields below. Degradation is a property of the turn, not its outcome (§6). |
| 5 | Do **not** fire `handoff_to_hermes`. A handoff propagates an unknown memory state into another runtime, where it stops being visible. Hand off only if the ack says so in as many words. |

#### §3.1 A turn ack goes in `loop_acks`, never in `approvals[]`

`approvals[]` is not a general log of things a human said yes to. It is **G-5/G-6's destructive-operation
surface**, and putting a turn ack there breaks the gate in both directions. From
`ci/gates/check_rollback.py`:

```python
REQUIRED_APPROVAL_FIELDS = ["operation", "approved_by", "at", "blast_radius"]
...
if destructive:
    for i, ap_rec in enumerate(approvals):          # EVERY entry, not just the destructive ones
        missing = [f for f in REQUIRED_APPROVAL_FIELDS if not ap_rec.get(f)]
        ...
    if len(approvals) < len(destructive):            # a COUNT, not a pairing
```

| If the turn ack sits in `approvals[]` | What G-6 does |
|---|---|
| With `operation` + `ack` id only, as this skill used to say | **FAIL.** Every entry is validated once any destructive command is in `commands`, so a turn ack missing `at` and `blast_radius` fails a receipt whose destructive op was properly approved: `approvals[0] is missing ['at', 'blast_radius']` |
| With all four fields filled in, to satisfy that check | **Worse — a false PASS.** The gate pairs approvals to destructive ops **by count**, so a turn ack for a degraded brief satisfies G-6 for an unrelated `rm -rf`. Verified: one destructive command, one four-field turn ack, `G-5/G-6 PASS — 1 destructive op(s) approved` |

The second row is why "just add `at` and `blast_radius`" is the wrong fix: it converts a loud failure
into a silent one, and a silent one in the gate that exists to stop unapproved destruction. So:

- **A degraded-mode turn ack goes in `loop_acks`**, specified below.
- **`approvals[]` stays for g5/g6 operations only**, one entry per destructive command, each with all
  four fields including the blast radius **as understood at approval time**.

**`loop_acks` — the interim contract.** One entry per ack, appended in the turn it was granted:

| Field | Type | Holds |
|---|---|---|
| `condition` | string | The blocker code — `brief_degraded` or `brief_no_revision_marker`. The same value as `payload.blocker` on the turn's events |
| `operation` | string | The `operation` string for that condition, verbatim from §3 |
| `ack_id` | string | The id the approver returned. **Never** a string the seat composed |
| `human_granted_by` | string | **Required. The human who granted it.** A person, never a seat id — not `bot-00-programming-lead`, not "LEAD", not "the desk". If no human granted it, there is no ack and the field has no honest value |
| `relayed_by` | string \| null | Optional, and only a relay: the seat that carried the ask to the human and the answer back, normally `bot-00-programming-lead`. `null` when the seat asked a human directly |
| `at` | ISO-8601 | When it was granted, not when the receipt was written |
| `scope` | string | The one ticket and one turn it covers, named. An ack does not generalise |

**The grantor is a human, and the relay is not the grantor.** Degraded mode exists because the memory
plane cannot tell the seat what the desk already decided; the whole value of the ack is that a person
who *does* know said go ahead. A build seat asks LEAD and LEAD asks Ove (§3 step 2) — so on a build
seat's receipt, `relayed_by` is `bot-00-programming-lead` and `human_granted_by` is **Ove**, the
person at the end of that chain. A single `granted_by` field could not express this, and the shape it
permitted — one complete-looking entry naming only a seat — is a degraded turn with no human in it at
all, which is the thing §3 forbids, recorded as though it complied.

So, fail closed:

| `loop_acks` entry | Verdict |
|---|---|
| `human_granted_by` absent, or empty | **No ack.** The turn is blocked (§3, last row) — it is not an ack with a missing field |
| `human_granted_by` matching `^bot-0[0-6]-` , or `LEAD`/`QUALITY`/a seat label | **No ack**, and worse than absent: it names a bot where a person is required, which reads as compliance to anyone skimming |
| `human_granted_by` a person, `relayed_by` a seat or `null` | A recorded ack |

**LEAD is not exempt.** LEAD's own degraded turns are acked by Ove in the 1:1, so LEAD's
`human_granted_by` is Ove and its `relayed_by` is `null` — LEAD relays *for other seats*, and cannot
relay for itself. A receipt where `human_granted_by` is a seat is invalid whichever seat wrote it.

**No gate reads `loop_acks`, and that is deliberate but incomplete.** Deliberate, because
`ci/gates/check_rollback.py` must not see it — being counted as a destructive-op approval is the
whole defect this field exists to avoid. Incomplete, because it means nothing validates the shape
either: a seat can write a malformed entry, or omit the field after getting an ack, and no gate will
say so.

**How presence is checked, today and properly.** Today: by review. A degraded turn is visible in the
receipt's `unverified` (§3 step 3) and in `payload.degraded` on its events, so a reviewer who sees
either and no matching `loop_acks` entry has found an unacknowledged degraded turn. That is a human
check, and this skill is the only thing asserting it. Properly, and this is the ask on QUALITY:
`skills/verification-receipts/SKILL.md` carries the shared receipt contract and is
`bot-06-quality-security`'s, so the field belongs there, with a G-2 rule that is cheap to state —
**if any command or claim in the receipt records a degraded turn, `loop_acks` must hold an entry
whose `condition` matches and whose six fields are all present** — and which must not be added to
`check_rollback.py`, where the count would reintroduce the hazard. Recorded in the receipt's
`blockers` with that wording.
- **A turn ack is not an `approval_id`** and never substitutes for one (§3, below). The field split is
  the mechanical expression of a rule this skill already had in prose.

**One field per meaning.** A degraded event carries three separate things — *which desk rule fired*,
*what the upstream said*, and *where it said it* — and they do not fit in one `reason` key. Use these
payload names, on `implementation.*` and on `ticket.blocked` alike:

| Payload field | Holds | Example |
|---|---|---|
| `degraded` | `true` on any turn worked under either condition | `true` |
| `blocker` | The **desk blocker code** from the table above — one of two fixed strings | `"brief_degraded"` |
| `upstream_reason` | The **verbatim `reason` string** the tool returned, uninterpreted. Omit on the no-marker condition; there is no upstream failure to quote | `"substrate returned HTTP 502"` |
| `reason_path` | The **field path** `upstream_reason` was read from (below). Omit when `upstream_reason` is omitted | `"recall.results[pd-desk].reason"` |
| `ack` | The recorded ack id — never one you typed | `"ack-2026-09-30-004"` |

`blocker` and `upstream_reason` are not interchangeable: a consumer filters on `blocker` and a human
reads `upstream_reason`, and collapsing them into a single `reason` loses whichever one you did not
write. **Do not use a bare `payload.reason` for either** — it is the field that had two meanings.

These five names are LEAD's convention for this loop, not a catalogue contract:
`docs/handoff-contracts.md` defines the event *kinds*, not these payload keys, and `desk_event_emit`
types `payload` as a free `object`, so nothing validates them. Publishing them there is a G-4 change
and QUALITY's to make. Two names are **not** available: the gateway injects `seat`, `event` and
`task_id` into every payload and your keys are merged **over** them (§6), so never set those three.

**There are four places a `reason` can live, and the ask, the receipt and the event must quote the
one that actually fired:**

| Failure | Quote from | Name it as |
|---|---|---|
| Call-level, Shape A (`unknown_tool`, `deadline`, `forbidden`, `invalid_args`, `secret_refused`, `backend_missing`, `internal`) | the **top-level** `reason` | `reason` (top level), **with the `error` code** |
| Substrate brief, Shape B | `substrate.reason` | `substrate.reason` |
| Recall, substrate fallback branch, Shape B | `recall.reason` | `recall.reason` |
| Recall, Hindsight branch, Shape B (per bank) | `recall.results[i].reason` | `recall.results[<bank>].reason`, **with the bank name** |

Row 1 is the one the earlier wording made unusable: it told every seat there was no top-level
`reason` and to quote a nested one, which on a Shape A response leaves nothing to quote and no way to
follow step 2 or step 3 at all. A `deadline` or an `unknown_tool` brief has a real reason string —
it is just at the top level, next to the `error` code that names the refusal, and the code belongs in
the ack alongside it.

The per-bank row is the one most easily lost, because the round that added per-bank *detection*
(§2.1) is not the same thing as per-bank *reporting* — and "recall failed" without the bank and its
reason sends whoever reads the receipt looking in the wrong plane. Quote the bank: `pd-desk` timing
out and `pd-<seat>` timing out are different incidents with different blast radius.

If the ack does not come, or is refused, the turn stops and **that** is the `ticket.blocked` case:
emit it with `payload.blocker` set to the condition's code, plus `upstream_reason` and `reason_path`
where there is one. Its consumer is LEAD, which is correct for a turn that produced nothing and needs
a decision.

An ack authorises **one turn** of repo work on **one ticket**. It is not an `approval_id` for a g5
or g6 tool and does not substitute for one — which is why it lives in `loop_acks` and not in
`approvals[]` (§3.1). **Never type an ack id you were not given** — a
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

#### §4.1 The approval must be bound to a sha, and must not create one

Leave `approved_by` unset. A seat never stamps its own work, and G-2 failing closed on an unstamped
receipt is the designed state. The rest of this section is about why the **stamp itself** is not a
receipt-file edit, because two separate defects meet here and each one on its own looks like a small
bug in a tool.

**Defect 1 — the stamping tool deadlocks on its own input.** `desk_receipt_approve` gates the
receipt before it stamps:

```python
# services/desk-gateway/src/desk_gateway/tools/quality.py — receipt_approve
check = await repo.receipt_check(receipt, receipt.get("bot") or "", False, args["receipt_path"])
if not check.get("ok"):
    return failure("gate_failed", "the receipt does not pass G-2/G-3/G-5/G-6 before stamping", …)
receipt["approved_by"] = ctx.bot_id          # ← never reached on a first stamp
```

`repo.receipt_check` writes the receipt **as fetched** to a scratch file and runs G-2 over it, and
`ci/gates/check_receipt.py` fails an absent `approved_by` unconditionally — not behind `--strict`,
and the preflight passes `strict=False` anyway. So the one state the tool exists to change is the one
state it refuses: every correct unstamped receipt returns `gate_failed`, forever. Verified: G-2
non-strict on an unstamped receipt exits 1 with `'approved_by' is missing`.

**Defect 2 — and this is the one that rules out the obvious workaround.** The workaround for defect 1
is to skip the tool: QUALITY reviews tip X and lands the stamp as a hand-written commit. That
cannot work, and not because of a bug — because of what a commit is. **Writing the approval into a
file on the branch creates a new tip Y.** Greptile's COMPLETED and the reviewed sha in the
`approval_note` both name X, and the merge head is now Y, which nothing has reviewed. Review Y and
the stamp for it creates Z. **Advancing the tip is not a side effect of the stamp; it is the stamp** —
an approval delivered as a commit can never describe the head it is committed to. Three pushes on
this branch are the demonstration: each one moved the head past the tip the previous review covered.

So a receipt-file stamp is wrong in both directions at once. It is **unbound** — it asserts a sha in
prose, and nothing checks that the sha it names is the head — and it is **tip-creating**. The rule
that falls out:

> **An approval must be bound to a sha, and must not create one.**

**What satisfies that, in preference order.** All three are foreign changes; none is a LEAD edit.

| Mechanism | Bound to a sha? | Creates a commit? | Notes |
|---|---|---|---|
| **A GitHub check run on the reviewed sha** — `POST /repos/{repo}/check-runs` with `head_sha`, a fixed `name` like `desk/quality-approval`, `conclusion: "success"` | **Yes, by construction** — the API takes the sha as a required field | **No** | Preferred. The gateway already holds a GitHub token (`upstreams.GitHub`), so this is a new method beside `comment_on_issue`, not new plumbing. A push to a new head simply has no such check run, which is the correct behaviour rather than a staleness problem to manage |
| **A PR review approval** | Yes — GitHub marks a review stale when the head moves | No | Human-visible and needs no new tool, but a review is by a GitHub user; mapping one to `bot-06-quality-security` is a convention the gate would have to encode |
| **A gateway-store record**, keyed by `(receipt_path, reviewed_sha)` | Yes, if the sha is part of the key | No | There is already a precedent for a no-commit approval: `contract_ack` records acks through `store.record_ack` and commits nothing. But the store's reader returns its default on `OSError`/`JSONDecodeError` (§2.1), so a corrupt store silently loses the approval. That fails **closed** — G-2 goes red, not green — so it is survivable, but it is the weakest of the three and invisible on the PR |

**What the receipt carries instead of a stamp.** Not the approval — a **pointer** to where the
approval lives, so the gate can resolve it against the head at gate time:

```jsonc
"approval_ref": {
  "kind": "check_run",                    // check_run | pr_review | gateway_store
  "name": "desk/quality-approval",        // what to look for
  "reviewed_sha": "<40 hex>",             // the sha the reviewer actually read
  "resolved_by": "G-2 at gate time"       // never by the authoring seat
}
```

`reviewed_sha` is recorded by the *reviewer's* mechanism, not typed by the authoring seat, and G-2's
job becomes: resolve `approval_ref` for the **current head**, and pass only if an approval exists for
that exact sha. That is what makes tip matching mechanical instead of a sentence in a note that
nobody can check.

**What is still not a fix**, under any of this: a seat writing a placeholder into `approved_by` to
get a preflight past itself. That fabricates the independent review the gate exists to require, and
an empty string fails identically — `if not approved_by` catches both.

**Ownership, plainly.** `services/**` is `bot-01-systems-backend`'s, `ci/gates/**` and
`contracts/tool-rosters/**` are `bot-06-quality-security`'s. Closing this needs one change in each:
a gateway tool that records a sha-bound approval without committing, and a G-2 that resolves
`approval_ref` against the head instead of reading `approved_by` from the file. Both are specified
with the proposed patches in the receipt's `blockers`. Until they land, **this PR's approval is not
obtainable by any mechanism that leaves the reviewed tip intact**, and that — not a missing stamp —
is what the red G-2 on this receipt records.

### §5 Phase 3 — memory_write

One fact per call, with its evidence, per `skills/hindsight-memory` §3. The loop adds only this:
**the write happens in the same turn as the work**, not "later". A turn that ends without it leaves
the next brief describing a desk where this turn did not happen.

`memory_write` is a `write`, so it fails **closed** in the sense that matters for the gate: an error
is returned as an error rather than swallowed. **It is not atomic, and `ok: true` is not proof the
fact is in every plane.**

`core.memory_retain` writes to **two planes** and reports each one:

```python
results["hindsight"] = await svc.hindsight.retain(...)   # only when Hindsight is configured
results["substrate"] = await svc.substrate.call_tool("memory_write", ...)
ok = any(not r.get("error") for r in results.values())   # ← ANY, not all
if not ok:
    return failure("memory_unavailable", "no memory plane accepted the write", results=results)
return {"ok": True, "bank": ctx.seat.memory_own, "results": results}
```

**So read `results`, not `ok`.** `ok: true` with `results.hindsight.error` set means the bank-scoped
memory your own next brief recalls from did not take the write; `ok: true` with
`results.substrate.error` set means the `graph:<graph_id>` scope did not. Either way the fact is in
one plane and missing from the other, and the next brief is correspondingly incomplete.

| What came back | What it means | What you do |
|---|---|---|
| `ok: true`, no `error` in either entry | Both planes accepted | Nothing more |
| `ok: true`, an `error` in one entry | **Partial success.** The fact is in one plane only | Record it in `unverified`, naming the plane that failed and its `reason`, and claim the retain only for the plane that took it. Do not report "retained" flat |
| `error: "evidence_required"` or `"secret_refused"` | Refused **locally**, before either upstream was called | **Nothing was written.** Fix the call (add `receipt_path`/`source`, remove the credential shape) and call again — this is the one safe retry |
| `error: "memory_unavailable"` with `results` | Neither plane returned success. Each entry's `error`/`reason` says why | Per entry: a refusal (4xx, `not_configured`) wrote nothing; a timeout or transport error is **unknown**, see below |
| Top-level `error: "deadline"` — the 20 s cut, with no `results` at all | **Unknown.** The gateway abandoned the call; either plane may have committed after it stopped listening | See below. Do not record it as "nothing retained" |

**An error is not proof that nothing was retained.** The two local refusals above are, because they
return before any upstream call. Everything else can be a commit the client did not see: the upstream
accepted the write and the response was lost to a timeout or a reset. Treating that as *none* is the
same envelope-reading mistake as §2.1, one plane further down.

**There is no idempotency key, so a blind retry can duplicate the fact.**
`contracts/tool-rosters/_core.yaml` gives `desk_memory_retain` no idempotency or dedup input and the
schema is `additionalProperties: false`, so you cannot add one — and two retains of the same decision
are two rows the weekly reflect will weigh against each other as if they were independent
observations. So, on an **uncertain** outcome:

1. `desk_memory_recall` on the same content first, and only retain again if it is genuinely absent.
   That read is not conclusive either — recall is a search, not a key lookup — so treat a miss as
   "probably absent", not "certainly absent".
2. If you do retry, **retry at most once**, and say so in `unverified`: "retained after a `deadline`
   on the first call; a duplicate row is possible".
3. If you do not retry, say that instead: "`desk_memory_retain` timed out; whether the fact was
   retained is unknown and it was not re-attempted".

Either way the receipt carries the per-plane outcome, and neither the receipt nor the event claims
more than `results` supports. A partial or uncertain write is a real result to report, not a blocker
to hide and not a success to round up. If no plane took it and nothing is uncertain, that is a
blocker — and the receipt is still the durable record.

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

#### §6.1 On the gateway path the catalogue kind is not the routing field

**Do not assume a consumer can route on the top-level `kind` of a `desk_event_emit` row.** It cannot.
`core.event_emit` does not pass your `kind` through — it builds a fixed envelope:

```python
event = {
    "kind": "note",                                        # ← every desk event, always
    "summary": f"{SEAT_LABEL[ctx.short]} {args['kind']}",  # ← "Systems & Design (SYSTEMS) implementation.completed"
    "graph_id": args.get("graph_id"),
    "payload": {"seat": ctx.short, "event": args["kind"], "task_id": args.get("task_id"), **payload},
    "actor": "agent",
}
```

So the catalogue kind you pass survives in **`payload.event`** and in the `summary` string, and the
top-level `kind` is the literal `"note"` on an `implementation.completed` and on a `ticket.blocked`
alike. Three consequences, and none of them is optional reading:

| | |
|---|---|
| **What consumers must route on** | `payload.event` — the catalogue kind, verbatim — plus `payload.seat` for the emitter. A consumer filtering `kind == "implementation.completed"` matches **nothing** the gateway ever wrote, and one filtering `kind == "note"` matches every desk event of every type |
| **What you still pass** | The catalogue kind, exactly as before and exactly as `docs/handoff-contracts.md` spells it. It is the value that lands in `payload.event`; passing `"note"` yourself would put `"note"` there and destroy the only routing information the row has |
| **Three payload keys are the gateway's** | It injects `seat`, `event` and `task_id`, and merges your `payload` **over** them (`**payload` comes last). So a payload of your own carrying `event` silently overwrites the routing field, and one carrying `task_id` overwrites the ticket id. **Never set `seat`, `event` or `task_id` in a payload you pass** |

**This is a documented contract gap, not a design.** `docs/handoff-contracts.md` describes typed
kinds with per-kind consumers, and the gateway emits one untyped kind for all of them. Closing it is
QUALITY's change (G-4) and it is one of two: give `desk_event_emit` a `kind` passthrough so the
envelope carries the catalogue type, or state in the catalogue that the gateway path routes on
`payload.event`. **Until one of those lands, a seat must not claim its emission routed anywhere** —
the honest receipt line is that the row was written with `payload.event` set and that whether a
consumer reads it is unverified. Raised in the receipt's `blockers`.

The substrate/connector `events_emit` is a **different tool** and this section is not evidence about
it: whether it preserves a typed kind was not observed. Read its own contract before assuming either
shape.

#### §6.2 Degradation goes in the payload

**A degraded turn (§3) is signalled in the payload, never by swapping the kind.** The kind says what
happened to the work; `payload.degraded` says what the seat knew while doing it:

| The turn | Kind (→ `payload.event`) | Payload |
|---|---|---|
| Completed, brief fine and marker recorded | `implementation.completed` | `receipt_path` |
| Completed, degraded (either §3 condition), ack recorded | `implementation.completed` | `receipt_path`, `degraded: true`, `blocker`, `upstream_reason` + `reason_path` where there is one, `ack` |
| Stopped — no ack, or ack refused | `ticket.blocked` | `blocker`, `upstream_reason` + `reason_path` where there is one |

`implementation.completed` is what carries finished work and its receipt to the integrator and
QUALITY; `ticket.blocked` is a blocker escalated to LEAD. Labelling a finished degraded turn
`ticket.blocked` would report a blocker for work that is actually sitting ready for review — the
receipt would say one thing and the event log another, and the seat waiting on LEAD would be waiting
for nothing. On the gateway path that mislabelling lands in `payload.event` and in the `summary`
rather than in the top-level `kind` (§6.1), which makes it *less* visible, not more forgivable.

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
| Edit on `brief_read_at` + `cached` alone, with no marker and no ack | §2.2, §2.3 — recording when you read is not the revision marker the precondition asks for |
| Report a brief as *failed* because the tool's contract has no etag field | §2.3 — that is an outage that did not happen; the no-marker condition is its own thing, with its own ack |
| Read the envelope as the answer — top-level fields present, so "it worked" | §2.1 — a completed `desk_brief` returns a full object on failure; the verdict is `substrate.error`, `recall.error` **and** every `recall.results[].error` |
| Go straight to the nested fields without checking for a top-level `error` | §2.1 — a Shape A refusal (`unknown_tool`, `deadline`, …) has no `substrate` or `recall` field at all, and its `reason` is at the top level |
| Check `recall.error` only | §2.1 — with Hindsight configured that field is never set; failures are reported per bank in `recall.results[]` |
| Record `generated_at` as `brief_etag`, or diff it | §2.2 — it is a read timestamp; it moves on every fresh call and freezes for five minutes on a cache hit |
| Record `cached` as a value the response carried when the key was absent | §2.2 — the fresh path never sets it; absent means `false`, and it is not a §2.1 failure |
| Retry a failed brief in a loop | One retry, then degraded. The audit log fills with the same refusal |
| Treat an empty brief as "nothing known" | It fails open. Empty plus a `reason` is *unknown* |
| Read `ok: true` from `desk_memory_retain` as "the fact is in memory" | §5 — `ok` is `any()` over two planes; one may have refused while the other took it |
| Treat a `desk_memory_retain` error as proof nothing was retained | §5 — only the two local refusals prove that; a timeout can follow an upstream commit |
| Retry an uncertain retain blindly | §5 — the roster accepts no idempotency key, so the same fact lands twice and the reflect weighs them against each other |
| Claim a `desk_event_emit` row routes on its top-level `kind` | §6.1 — the gateway writes `kind: "note"` for every kind; the catalogue type is in `payload.event` |
| Put `seat`, `event` or `task_id` in a payload you pass | §6.1 — your keys merge over the gateway's, so you overwrite the routing field or the ticket id |
| Put the blocker code and the upstream reason in one `payload.reason` | §3 — one of the two is lost; they are `blocker` and `upstream_reason`, with `reason_path` for where it came from |
| Call a raw docs or memory server | §4 — un-audited, needs a credential the seat must not hold |
| Install, edit or approve a skill for itself | §4 — unreviewed instructions, no receipt, no `skills.approve` |
| Edit a foreign path to "finish the feature" | G-1. Cross-seat work is contract-first |
| Mint an event kind | §6 — nothing consumes it |
| Swap a kind to signal degradation | §6.2 — a finished turn labelled `ticket.blocked` reports a blocker for work that is ready for review, in `payload.event` and the summary where it is harder to spot |
| Put a degraded-mode turn ack in `approvals[]` | §3.1 — G-6 validates every entry when a destructive command is present, and pairs approvals to destructive ops by count; a turn ack there either fails a properly-approved receipt or silently satisfies G-6 for an unrelated destructive op. It goes in `loop_acks` |
| Record a seat id as the ack's grantor | §3.1 — degraded mode needs a *human*; a seat in `human_granted_by` is a turn with no human in it, recorded as though it complied. LEAD is not exempt: it relays for others and cannot relay for itself |
| Invent an ack id, an `approval_id`, or a packet signature | PD-5, G-3 — a fabricated approval with an audit trail |
| Claim done without a receipt | G-2. A claim without a command is a guess with confident phrasing |
| Hand off a goal that already has an Agent Bus job | Two branches, one goal, a merge race a human untangles |

---

## Worked examples

**Good — SYSTEMS, one ticket, gateway brief (the common case today).**

```
desk_brief {graph_id: "ut-…", task_id: "intake-ack-idempotent"}
  → {seat, generated_at: 1790761742.31,          ← NO top-level error → Shape B  ✔ §2.1
     substrate: {ok: true, brief: "…"},          ← no .error  ✔ §2.1
     recall: {banks: ["pd-systems","pd-desk"],
              results: [{bank: "pd-systems", ok: true, …},
                        {bank: "pd-desk",    ok: true, …}]},  ← no .error on EITHER bank ✔ §2.1
     loaded_packs, intake_queue, reminders}
    No `cached` key at all → cached: false (fresh call). §2.2
    Brief SUCCEEDED. recall shows a 2026-09-24 decision on the ack path.
receipt stub: task_id, brief_read_at: 1790761742.31, cached: false   ← §2.2 row 2, NOT brief_etag
    …but no revision marker, and the ticket is an edit → §2.3 middle row. Ask before touching it.
→ LEAD (priority false): "desk_brief succeeded (no substrate/recall error). Its contract exposes no
   etag, so I cannot detect a change under me. Intending to edit
   services/desk-gateway/src/…/intake.py. Ack to proceed?"   → ack-2026-09-30-011
receipt: loop_acks[{condition: "brief_no_revision_marker",       ← NOT approvals[] — §3.1
  operation: "degraded-loop: repo work on a brief with no revision marker",
  ack_id: "ack-2026-09-30-011", human_granted_by: "Ove",   ← a person, never a seat id
  relayed_by: "bot-00-programming-lead",                   ← LEAD carried the ask; it did not grant it
  at: "2026-09-30T09:14:02Z", scope: "one turn, ticket intake-ack-idempotent"}]
desk_ownership_resolve {paths: ["services/desk-gateway/src/…/intake.py"]}  → bot-01  ✔ mine
desk_event_emit {kind: "implementation.started", graph_id, task_id,
  payload: {degraded: true, blocker: "brief_no_revision_marker", ack: "ack-2026-09-30-011"}}
    ← no upstream_reason / reason_path: nothing upstream failed.  No `event`/`seat`/`task_id` in the
      payload — the gateway sets those, and a key of mine would overwrite them (§6.1).
… edit, run the tests, record cmd + exit_code in the receipt …
desk_memory_retain {content: "Intake ack replays are collapsed on idempotency_key in the gateway,
  not the queue; window is 30 days", receipt_path: ".receipts/bot-01-systems-backend/…json",
  graph_id, task_id, tags: ["intake","idempotency"]}
  → {ok: true, bank: "pd-systems",
     results: {hindsight: {ok: true, …}, substrate: {ok: true, …}}}   ← BOTH planes, checked  ✔ §5
desk_event_emit {kind: "implementation.completed", graph_id, task_id, payload: {receipt_path: "…",
  degraded: true, blocker: "brief_no_revision_marker", ack: "ack-2026-09-30-011"}}
unverified: ["desk_brief exposes no etag, so it is unknown whether the brief changed during the
  turn; repo work proceeded under ack-2026-09-30-011",
  "desk_event_emit writes kind 'note' and carries the catalogue kind in payload.event; whether a
  consumer routes on that field is not verified from here"]
Desk post: "awaiting-review / pending QUALITY" + receipt path.  No handoff — SYSTEMS did the work.
```

The seat classified the shape first, then read both nested error fields, so a real success was
treated as one — no "substrate down" that never happened. It still asked for an ack, because a
succeeded brief with no marker leaves the precondition unmet and `brief_read_at` is a record rather
than a licence. It read `results` on the retain rather than `ok`, and it did not claim its event
routed anywhere.

**Good — same seat, brief failed, ack recorded, work finished.**

```
desk_brief {…} → {seat, generated_at: 1790762100.04,          ← no top-level error → Shape B
     substrate: {error: "upstream_error", reason: "substrate returned HTTP 502"},   ← FAILED
     recall: {banks: [...], results: [], error: "upstream_error", reason: "…"},
     loaded_packs, intake_queue, reminders}
  A fully populated response. Top level looks fine; substrate.error is what decides.  ← §2.1
  One retry, still 502 → DEGRADED, condition 1 (brief failed).
→ LEAD (priority false): "desk_brief degraded: substrate.error=upstream_error,
   substrate.reason='substrate returned HTTP 502'. Intending to edit
   services/desk-gateway/src/…/intake.py. Ack to proceed?"   → LEAD ↔ Ove → ack-2026-09-30-004
receipt: loop_acks[{condition: "brief_degraded",                 ← NOT approvals[] — §3.1
  operation: "degraded-loop: repo work without a memory brief",
  ack_id: "ack-2026-09-30-004", human_granted_by: "Ove",
  relayed_by: "bot-00-programming-lead", at: "2026-09-30T09:41:11Z",
  scope: "one turn, ticket intake-ack-idempotent"}];
  approvals: []                                                  ← no g5/g6 op in this turn
  unverified: ["substrate.reason 'substrate returned HTTP 502'; recall.error also set; prior
  decisions on this ticket unknown"]; brief_etag: null, brief_read_at: null
desk_event_emit {kind: "implementation.started", …, payload: {degraded: true,
  blocker: "brief_degraded",                          ← the desk rule that fired
  upstream_reason: "substrate returned HTTP 502",     ← verbatim, uninterpreted
  reason_path: "substrate.reason",                    ← where it was read from
  ack: "ack-2026-09-30-004"}}                         ← three meanings, three fields (§3)
… work, tests, receipt …
desk_event_emit {kind: "implementation.completed", …, payload: {receipt_path: "…",
  degraded: true, blocker: "brief_degraded", upstream_reason: "substrate returned HTTP 502",
  reason_path: "substrate.reason", ack: "ack-2026-09-30-004"}}  ← completed, NOT blocked (§6.2)
No handoff_to_hermes — the ack did not cover one.
```

The work is finished and reaches the integrator and QUALITY as finished work. `payload.degraded`
tells a later reader the seat was flying without the brief, `blocker` is what a consumer filters on,
and `upstream_reason` + `reason_path` are what a human needs to investigate the 502 — none of the
three standing in for another. Had the ack never come, the turn would have stopped and emitted
`ticket.blocked` with the same `blocker`/`upstream_reason`/`reason_path` triple — and produced no
diff.

**Good — the same brief, refused at the call level (Shape A).**

```
desk_brief {graph_id: "ut-…", task_id: "…"}
  → {error: "unknown_tool", reason: "desk_brief is not on the systems roster; a tool the gateway
     did not list does not exist"}
  A two-key object. No `seat`, no `substrate`, no `recall` — nothing nested to check.  ← §2.1 Shape A
  Reading substrate.error here would read `undefined` and pass.
→ LEAD: "desk_brief degraded: error=unknown_tool, top-level reason='desk_brief is not on the
   systems roster…'. No brief tool on this seat at all. Intending to edit …. Ack to proceed?"
receipt: loop_acks[{condition: "brief_degraded", operation: "degraded-loop: repo work without a
  memory brief", ack_id: "…", human_granted_by: "Ove", relayed_by: "bot-00-programming-lead",
  at: "…", scope: "one turn, one ticket"}];
  unverified: ["desk_brief returned error=unknown_tool at the top level (reason: '…'); the seat has
  no brief tool, so no prior decision on this ticket was read"]
desk_event_emit {kind: "implementation.started", …, payload: {degraded: true,
  blocker: "brief_degraded", upstream_reason: "desk_brief is not on the systems roster; a tool the
  gateway did not list does not exist", reason_path: "reason"}}    ← top level, named as such
```

The ask, the receipt and the event all quote the field that actually carried the reason. Under the
earlier wording — "there is no top-level `reason`, do not look for one" — this turn had nothing to
put in step 2 or step 3, which is why §2.1 classifies the shape before it judges it.

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

**Bad — the retain is read as atomic, twice over.**

```
desk_memory_retain {content: "…", receipt_path: "…", graph_id, task_id}
  → {ok: true, bank: "pd-systems",
     results: {hindsight: {ok: true, …},
               substrate: {error: "upstream_error", reason: "memory_write returned HTTP 503"}}}
Seat reads ok: true, records "decision retained", moves on.
… later, a second fact, and this time …
desk_memory_retain {content: "…"} → {error: "deadline", reason: "desk_memory_retain did not finish
  within 20s"}
Seat reads "write failed closed → nothing retained", calls it again immediately, and gets ok: true.
```

Two defects, one cause. The first call put the fact in Hindsight and **not** in the
`graph:<graph_id>` substrate scope — `ok` is `any()`, not `all()` (§5) — so a later reader of that
graph's memory sees nothing and the receipt says "retained" without qualification. The second call
may well have committed upstream before the 20 s cut, so the immediate re-call retained the same
decision twice, with no idempotency key to collapse them; the weekly reflect now has two rows that
look like two independent observations of the same thing. Correct: read `results` per plane and put
the failed plane in `unverified`; on the `deadline`, `desk_memory_recall` first and say in
`unverified` that a duplicate is possible if you do retain again.

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
| Failed brief read as successful | Populated response, no top-level `reason`, so no ack was sought | §2.1 — `substrate.error`, `recall.error` and `recall.results[].error` decide, nothing else |
| Call-level refusal read as a successful brief | `{error: "unknown_tool"}` or `{error: "deadline"}`; the seat checks `substrate.error`, finds nothing, and proceeds | §2.1 — classify the shape on the top-level `error` first; Shape A has no nested fields |
| Ack asked for with no reason to quote | Shape A response; the skill said there was no top-level `reason`, so step 2 had nothing in it | §3 — row 1 of the reason-path table: quote the top-level `reason` with its `error` code |
| Edit on a succeeded brief with no marker and no ack | Receipt has `brief_read_at` + `cached` and no `loop_acks` entry | §2.3 — the no-marker condition needs its own ack; the timestamp is a record, not a licence |
| A no-etag contract reported as an outage | "Brief failed, substrate down" on a brief whose nested fields were all clean | §2.3 — absence of an etag field is not a failure; it is the middle row, with the no-marker ack |
| `ok: true` retain read as "the fact is in memory" | One plane refused; `graph:` scope or the seat bank is missing the fact and the receipt says "retained" | §5 — read `results` per plane; record the failed plane in `unverified` |
| Retain error read as "nothing was written" | A `deadline` or transport error treated as *none*; the fact may be upstream already | §5 — only `evidence_required` and `secret_refused` prove nothing was written |
| Uncertain retain retried blindly | Two rows for one decision; the reflect weighs them as independent observations | §5 — `desk_memory_recall` first; no idempotency key exists, so say a duplicate is possible |
| Event assumed to route on its `kind` | Consumer filters `kind == "implementation.completed"` and matches nothing; handoff never happens | §6.1 — the gateway writes `kind: "note"`; the catalogue type is in `payload.event` |
| Payload carries its own `event`, `seat` or `task_id` | The seat's key merges over the gateway's and wipes the routing field or the ticket id | §6.1 — never set those three |
| Blocker code and upstream reason in one `payload.reason` | Either the filterable code or the diagnostic is lost from the row | §3 — `blocker`, `upstream_reason`, `reason_path` |
| Absent `cached` recorded as a returned value, or read as an incomplete brief | A fresh brief looks broken, or the receipt claims a field the response never carried | §2.2 — the fresh path never sets the key; absent means `false` |
| Failed Hindsight recall read as successful | `recall.error` absent because that path never sets it; the error sits in `recall.results[i]` | §2.1 — scan every bank entry; one failed bank is degraded |
| Partial recall worked around | `pd-<seat>` answered, `pd-desk` errored, seat proceeded on its own bank | The shared bank holds the desk's standing decisions; §3 applies |
| Ack or receipt says "recall failed" with no bank and no reason | Reader searches the wrong plane; the incident is undiagnosable later | §3 — quote `recall.results[<bank>].reason` and name the bank |
| Empty `loaded_packs` / `intake_queue` claimed as a fact | "No packs loaded" / "queue empty" asserted from a store file that may be unreadable | §2.1 — the store reader returns the default on `OSError`/`JSONDecodeError`; record it `unverified` as unread |
| "Confirming" the empty queue with `desk_roster_status` | Same `store.intake_counts()` call, same empty answer, now believed | §2.1 — there is no independent read; `unverified` is the answer |
| Loading or unloading a pack to inspect pack state | A write on a corrupt packs file reads `{}` and then overwrites it, destroying every seat's pack records | §2.1 — never diagnose with a write |
| Empty brief read as "none" | Confident claim about an untouched ticket that was not untouched | Check `reason`; degraded mode (§3) |
| Degraded work, no ack | No `loop_acks` entry; `unverified` silent on the brief | Get the ack before the edit; an ack cannot be back-dated |
| `loop_acks` entry naming a seat as the grantor | `human_granted_by: "bot-00-programming-lead"` — a complete-looking entry with no human in it, which reads as compliance | §3.1 — the grantor is a person; the relaying seat goes in `relayed_by`. Fail closed: a seat id there is no ack at all |
| Fabricated ack id | Receipt field satisfied, audit row matches no approval | PD-5 breach. Obtain a real one |
| Turn ack recorded in `approvals[]` | G-6 fails a receipt whose destructive op was properly approved — or, with all four fields, passes one that was not | §3.1 — `loop_acks` for turn acks, `approvals[]` for g5/g6 only |
| `approved_by` filled in to get `desk_receipt_approve` past its own preflight | The independent check is fabricated; an empty string fails identically | §4.1 — leave it unset. The approval is not a receipt-file stamp: it is sha-bound and commit-free, resolved from `approval_ref` |
| Nothing recorded about the brief | Reviewer cannot tell what state you read | `brief_etag`, or `brief_read_at` + `cached`, naming the field it came from (§2.2) |
| `generated_at` recorded as `brief_etag` | A staleness guarantee that does not exist; diffing it alarms on every fresh call and stays silent across a cache hit | §2.2 — it goes in `brief_read_at`; change detection is unavailable until the etag lands |
| Etag moved mid-turn (etag-bearing tool) | Two turns' claims disagree | Re-brief and re-read before claiming |
| No-marker ack asked for under the wrong operation | The receipt reads as an upstream outage; whoever reads it looks for a 502 that never happened | §2.3 — `…on a brief with no revision marker`, and no `upstream_reason` in the payload |
| Cache hit treated as a failed brief | An ack asked for under the `brief_degraded` code with nothing to quote | A cached brief is a brief; record `cached: true` and take the no-marker row like any other `desk_brief` turn (§2.2, §3) |
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
| A brief that succeeded per §2.1 **and** a revision marker per §2.2 before repo work; a recorded ack otherwise, one operation string per condition | G-2, PD-1 | Acting on unknown memory state is claiming without observing — and a read timestamp does not make the state known |
| Success is judged on every nested error field, never on the envelope | G-2, PD-1 | A fail-open read returns a full object; the top level cannot tell you it failed, and one code path reports per bank |
| No staleness claim the tool cannot support | PD-1, PD-6 | `generated_at` is when you read, not what you read; the gap goes in `unverified` |
| Degradation goes in the payload, never in the event kind | G-4 | A mislabelled turn is a blocker nobody owns or work nobody reviews — and on the gateway path the label sits in `payload.event`, not in a routable kind (§6.1) |
| One payload field per meaning: `blocker`, `upstream_reason`, `reason_path` | PD-1 | A single `reason` loses either the filterable code or the diagnostic |
| A human named in `human_granted_by` on every `loop_acks` entry, the relaying seat only in `relayed_by` | G-2, PD-5 | Degraded repo work is authorised by a person who knows what the brief could not tell the seat; a seat id there authorises nothing |
| Turn acks in `loop_acks`; `approvals[]` reserved for g5/g6 operations | G-6 | G-6 validates every `approvals` entry and pairs them to destructive ops by count — a turn ack there fails a good receipt or silently passes a bad one (§3.1) |
| `approved_by` left unset by the authoring seat, whatever the approval tool does | G-2, PD-5 | A placeholder fabricates the independent check. An approval must be bound to a sha and must not create one, so it does not live in the receipt file at all (§4.1) |
| Per-plane outcome of every `desk_memory_retain`, claimed no further than `results` supports | G-2, PD-1 | `ok` is `any()` over two planes, and an error is not proof that nothing was written |
| No claim that an emitted event reached a consumer | PD-1, PD-6 | The gateway collapses the catalogue kind to `note`; routing on the gateway path is unverified (§6.1) |
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
