---
name: desk-production-loop
description: The default production turn for a desk seat — memory_brief (+ etag) before any repo work, act inside owned paths, memory_write, events_emit, handoff_to_hermes. Use at the start of every ticket, before the first edit, and before any completion claim. Also use to decide whether a failed brief permits degraded mode.
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

**The one hard precondition: no repository work before a brief that returned an etag.** Reading
files is fine. Editing, committing, branching, pushing, opening a PR, or calling any `write` tool
is repo work, and all of it waits for the brief. A seat that edits first is deciding again
something the desk already decided, with no way to know it — and the memory plane it was supposed
to consult is the only place that record lives.

```
Ticket in hand. About to touch the repo?
│
├─ memory_brief called this turn?              NO ──▶ Call it. §2
│  │ YES
├─ It returned an etag?                        NO ──▶ DEGRADED. Human ack or stop. §3
│  │ YES
├─ Recorded the etag in the receipt?           NO ──▶ Record it, then act. §2
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

### §2 Phase 1 — brief, and the etag

Call `memory_brief` (or `desk_brief`) once at the start of the turn, with `graph_id` and `task_id`
when the ticket carries them. What comes back is the substrate brief for the graph, recall from
`pd-<seat>` and `pd-desk`, and the seat's open tickets — plus an **etag** identifying the exact
brief revision you read.

The etag is the thing that makes the brief evidence rather than atmosphere. Record it:

1. **In the receipt**, as `brief_etag`, alongside the `task_id`. A reviewer can then ask whether
   the decision you made was available to you when you made it.
2. **On the writes of this turn**, wherever the live schema accepts it, so `memory_write` and
   `events_emit` are attributable to the state you actually read.

Re-brief with `refresh: true` when the turn spans a long gap, after your own `memory_write` if you
need the fact back in the same turn, or when another seat may have written to `pd-desk` meanwhile.
**If the etag changed, re-read before you claim anything**: the brief you acted on is no longer the
current one, and the difference is where a contradiction hides.

The brief is cached five minutes at the gateway. A cached brief is still a brief and still carries
its etag; the cache is not a degraded state.

> **Not yet threaded through the roster.** `contracts/tool-rosters/_core.yaml` gives `desk_brief`
> no etag output field and `desk_memory_retain` / `desk_event_emit` no etag input, and every roster
> schema is `additionalProperties: false` — so passing one today is a validation error, not a hint.
> Until QUALITY lands that contract change (G-4), the receipt is the only place the etag is
> recorded, and the receipt is enough to satisfy this section. Record it from whatever the live
> `memory_brief` response calls it, and name that field in the receipt.

### §3 Degraded mode needs a human ack

`memory_brief` is a `read`, so it fails **open**: on an upstream failure you get an empty brief and
a `reason` string, not an error. That is the dangerous case, because an empty brief reads exactly
like a ticket nobody has touched.

**Degraded mode is any of:** the brief returned empty with a `reason`; the call was cut by the 20 s
deadline; the response carried no etag; or the connector did not list the tool.

In degraded mode you may read the repository and you may report. You may **not** do repo work
without a recorded human acknowledgement:

| Step | What it is |
|---|---|
| 1 | Stop before the first edit. Do not retry in a loop — one retry, then it is degraded. |
| 2 | Ask for the ack the way approvals are already routed: a build seat asks LEAD (priority false); LEAD asks Ove in the 1:1. State the tool, the verbatim `reason`, and what you intend to edit. |
| 3 | Record the returned ack id in the receipt under `approvals`, with `operation: "degraded-loop: repo work without a memory brief"`, and put the verbatim `reason` in `unverified`. |
| 4 | Act. Emit the turn's events with `degraded: true` in the payload so the event log shows which rows were produced without a brief. |
| 5 | Do **not** fire `handoff_to_hermes`. A handoff propagates an unknown memory state into another runtime, where it stops being visible. Hand off only if the ack says so in as many words. |

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
no consumer reads is a row nobody will ever act on. A degraded turn (§3) is therefore
`ticket.blocked` with `payload.reason: "brief_degraded"`, `payload.degraded: true` and the ack id —
not a new `loop.*` kind. A dedicated kind would be a welcome contract change; it is QUALITY's to
make (G-4).

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
| Edit before a brief with an etag, without a recorded ack | §2, §3 — the decision may already exist and you cannot see it |
| Retry a failed brief in a loop | One retry, then degraded. The audit log fills with the same refusal |
| Treat an empty brief as "nothing known" | It fails open. Empty plus a `reason` is *unknown* |
| Call a raw docs or memory server | §4 — un-audited, needs a credential the seat must not hold |
| Install, edit or approve a skill for itself | §4 — unreviewed instructions, no receipt, no `skills.approve` |
| Edit a foreign path to "finish the feature" | G-1. Cross-seat work is contract-first |
| Mint an event kind | §6 — nothing consumes it |
| Invent an ack id, an `approval_id`, or a packet signature | PD-5, G-3 — a fabricated approval with an audit trail |
| Claim done without a receipt | G-2. A claim without a command is a guess with confident phrasing |
| Hand off a goal that already has an Agent Bus job | Two branches, one goal, a merge race a human untangles |

---

## Worked examples

**Good — SYSTEMS, one ticket, brief available.**

```
memory_brief {graph_id: "ut-…", task_id: "intake-ack-idempotent"}
  → brief + etag "w/\"a41f…\"" ; recall shows a 2026-09-24 decision on the ack path
receipt stub: task_id, brief_etag: "w/\"a41f…\"" (from the memory_brief response)
desk_ownership_resolve {paths: ["services/desk-gateway/src/…/intake.py"]}  → bot-01  ✔ mine
events_emit {kind: "implementation.started", graph_id, task_id}
… edit, run the tests, record cmd + exit_code in the receipt …
memory_write {content: "Intake ack replays are collapsed on idempotency_key in the gateway, not
  the queue; window is 30 days", receipt_path: ".receipts/bot-01-systems-backend/…json",
  graph_id, task_id, tags: ["intake","idempotency"]}
events_emit {kind: "implementation.completed", graph_id, task_id, payload: {receipt_path: "…"}}
Desk post: "awaiting-review / pending QUALITY" + receipt path.  No handoff — SYSTEMS did the work.
```

The brief surfaced the existing decision, so the seat extended it instead of re-litigating it. The
etag says which revision it read, and the next seat's brief shows this turn.

**Bad — same ticket, brief down.**

```
memory_brief {…} → {} with reason: "substrate unreachable"
Seat reads it as "no prior decisions", edits the ack path, writes a receipt, retains
  "intake acks are not idempotent" with the receipt path, and reports done.
```

Four failures from one misread. The brief was *unknown*, not empty (§3). Repo work went ahead with
no ack. The retained "fact" now contradicts a decision that was already in `pd-desk`, and it is
retained with a receipt path, so it looks evidenced. The next seat's brief contains both, and the
weekly reflect resolves towards the newest — the wrong one. The correct turn: one retry, then ask
LEAD for the ack with the verbatim reason, and stop until it arrives.

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
| Edit before the brief | Receipt has no `brief_etag`; work contradicts a recorded decision | Brief first. It is the precondition, not a courtesy |
| Empty brief read as "none" | Confident claim about an untouched ticket that was not untouched | Check `reason`; degraded mode (§3) |
| Degraded work, no ack | No `approvals` entry; `unverified` silent on the brief | Get the ack before the edit; an ack cannot be back-dated |
| Fabricated ack id | Receipt field satisfied, audit row matches no approval | PD-5 breach. Obtain a real one |
| Etag not recorded | Reviewer cannot tell what state you read | Record it in the receipt, naming the response field it came from |
| Etag moved mid-turn | Two turns' claims disagree | Re-brief and re-read before claiming |
| Raw docs or memory call | No event row; retain outside `pd-<seat>` | §4 — substrate or gateway only |
| Seat enables its own skill | `installed_skills` disagrees with the pack at next doctor | List and invoke only, until `skills.approve` (§4) |
| Turn ends without `memory_write` / `events_emit` | Next brief shows the turn never happened | Both are in-turn, not follow-ups |
| New event kind | Rows nobody consumes | Use the catalogue; ask QUALITY for a kind (G-4) |
| Provisional packet field sent | Validation error, or false provenance | Omit until SPE-4792 lands; say unsigned |
| Handoff on a goal with a bus job | Two branches, one goal | Check receipts and open PRs first (`skills/agent-bus` §2) |

---

## Gate mapping

| Rule | Gate or directive | Why |
|---|---|---|
| Brief with an etag before repo work; ack recorded otherwise | G-2, PD-1 | Acting on unknown memory state is claiming without observing |
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
