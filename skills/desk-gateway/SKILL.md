---
name: desk-gateway
description: How to use the per-seat gateway tools: rosters as contracts, fail-open reads and fail-closed writes, gate tags, deadlines, 403 and not_configured handling.
bots: [all]
gates: [G-5, G-6, G-7]
---

# Desk Gateway

## When this applies (L1)

Every `desk_*` tool you hold comes from the Desk Gateway at `https://desk.swcstudio.space/mcp/<seat>`.
The gateway serves your roster and nothing else: **a tool the gateway did not list does not
exist**, and a call it refused is a blocker for LEAD, not a retry loop. Rosters are contracts
under `contracts/tool-rosters/` (QUALITY); the eight core tools are in `_core.yaml` and your seat
file adds the rest.

```
Calling a gateway tool?
│
├─ Is it in your tools/list right now?      NO ──▶ It does not exist for you. Ask LEAD. §1
├─ kind: read?  Empty result + reason ──▶ Fail-open. Record the reason; do not treat empty as "none". §2
├─ kind: write? Error ──▶ Fail-closed. Nothing happened. One retry only if the reason says so. §2
├─ gates: [g5]? ──▶ rollback_plan + approval_id required (PD-5). §3
├─ gates: [g6]? ──▶ approval_id required; echoed into the audit event. §3
├─ Took > 20 s? ──▶ The call was cut. Bound the inputs and split the work. §4
├─ 403? ──▶ Wrong seat endpoint. Stop. Tell LEAD. §5
├─ not_configured? ──▶ Upstream credential not provided. `unverified`, no browser workaround. §5
├─ desk_brief? ──▶ Read `substrate` and `recall` separately. The gateway cache is not the substrate cache. §7
├─ About to pass `profile`, `if_none_match`, or a bank name? ──▶ Not on the desk schema. The call is rejected. §7
└─ Argument contains a token, password or key? ──▶ Remove it. Every call is audited. §6
```

The gateway exists so that Bots hold no credentials and every action is on the event log. Both
properties only hold if the seat treats refusals as answers and arguments as public.

---

## Method (L2)

### §1 The roster is the contract

`tools/list` on your endpoint returns your seat's roster: the eight core tools plus 2–7 seat
tools, 10–15 in total, or up to 20 with one tool pack loaded (`skills/tool-packs`). Each tool
carries `kind` (`read` or `write`), `gates` (`g5`, `g6`, or none) and a JSON schema. The schema
is enforced: `additionalProperties: false` means an extra argument is a validation error, not
an ignored hint.

If a task needs a tool that is not on your roster, the answer is a contract change through
QUALITY (G-4), or a handoff to the seat that has it. Working around a missing tool with the
browser or the shell puts an un-audited action on a plane the gateway was built to fence.

### §2 Failure semantics by kind

| Kind | On upstream failure | What you do |
|---|---|---|
| `read` | Fails **open**: empty result plus a `reason` string | Record the reason. An empty result with a reason is "unknown", never "none". A claim built on it goes in `unverified` |
| `write` | Fails **closed**: an error, and the mutation did not happen | Do not assume partial effect. Retry once only if the reason is transient (the deadline was hit, the upstream was unavailable); otherwise report the blocker |
| `write` + `g5`/`g6` | Fails closed and refuses without the gate fields | A refusal is a blocker for LEAD. Never re-issue the call with invented `approval_id` |

The gateway never returns an upstream stack trace. If the `reason` is unhelpful, say so in the
receipt; do not guess at the cause.

### §3 Gate tags (PD-5)

| Tag | Required inputs | Where they come from |
|---|---|---|
| `g5` | `rollback_plan`, `approval_id` | The plan is yours and must satisfy G-5 (command, recovery time, data implications). The approval id is a recorded human approval, obtained the way `core-directives` routes it: build seats ask in the group or via LEAD; LEAD surfaces it to Ove |
| `g6` | `approval_id` | Same approval path. The id is echoed into the audit event, which is how the receipt and the event log agree |

An `approval_id` is a reference to an approval that exists. Typing a plausible string to satisfy
the schema is a PD-5 breach with an audit trail attached to it. If you do not have one, you do
not make the call.

Tools carrying these tags today: `desk_vercel_promote` (g5), `desk_vercel_rollback` (g5),
`desk_railway_redeploy` (g5), `desk_play_staged_rollout` (g5 g6), `desk_play_halt_rollout` (g6),
`desk_appstore_phased_release` (g5 g6), `desk_appstore_pause_release` (g6). Your roster file is
authoritative if this list drifts.

### §4 The 20-second deadline

Every call is cut at 20 seconds, under the MCP client's own deadline, so the client sees a clean
error rather than a hang. Consequences:

- Bound inputs that have a bound: `limit`, `lines`, `since_hours`, `timeout_sec` (for
  `desk_bus_wait_job`, poll in slices rather than one long wait).
- Split a large question into several calls; three calls that return beat one that is cut.
- A cut read returns empty with a `reason` naming the deadline. Treat it as §2, not as "the data
  is empty".

### §5 Errors that mean "stop"

| Error | Meaning | Response |
|---|---|---|
| `403` | Your token is for a different seat than the endpoint you called, or the connector was added with the wrong URL | Stop. Tell LEAD with the endpoint and tool name. Do not retry, do not try another endpoint. `/desk doctor` shows the Connector row |
| `not_configured` | The operator has not provided the upstream credential for that tool (Play, App Store Connect, Vercel, Railway, Greptile) | Record it in `unverified` with the tool name. Do not perform the action through the browser or a personal login; the gateway path exists so that the action is audited and the credential is not yours to hold |
| Refusal naming gate fields | A g5/g6 call without its approval or rollback inputs | Blocker for LEAD. Obtain the approval; do not invent it |
| Unknown tool | The tool is not on your roster (or a pack was unloaded) | §1. Check `tools/list`; do not guess a name |

### §6 Audit and arguments

Every call, successful or not, is written to the event log (Greptime `agent_events`) with seat,
tool, `graph_id`, `task_id`, outcome, duration and a hash of the redacted arguments. Pass
`graph_id` and `task_id` wherever the schema allows them, so the event can be tied to the ticket.

Arguments are redacted at the gateway, but redaction is a backstop, not permission. A token in
an argument is a token that left the Bot computer, was hashed into an audit row and may have
reached an upstream before redaction rules matched it. If a tool needs a secret, the gateway
already holds it; you never supply one (PD-4).

### §7 Brief pipeline, durability, and tools the roster did not gain

`desk_brief` still takes only `graph_id`, `task_id`, and `refresh`
(`contracts/tool-rosters/_core.yaml`). `additionalProperties: false` means `profile`,
`if_none_match`, or a bank name is a validation error.

`swcstudiospace/agent-substrate` was not readable from this seat (GitHub 404). Substrate
sentences below come from the history digest of main `feb597f` (`git log --stat` since 8 Oct
2026). A path is a path that commit's stat lists. The file was not opened. Where the digest
states a behavior and does not print an environment-variable name, the desk task's name is
given beside the SHA.

Two caches sit in front of a brief.

| Cache | Where | What a seat does |
|---|---|---|
| Gateway | `services/desk-gateway/src/desk_gateway/tools/core.py` `brief`: in-process, `BRIEF_TTL_SEC` 300. A hit adds `cached: true`. `refresh: true` skips it. A substrate error is not cached. The same function gathers `Substrate.brief` and `memory_recall` | Pass `refresh: true` after a retain you need in the same turn |
| Substrate | `40890e4` (PR #64): identical concurrent misses share one load; stale-while-revalidate for the brief is shadow by default. Stat: `packages/mcp-server/src/cache.ts`. Desk-task flag name: `SUBSTRATE_CACHE_SWR` | Do not set the flag. Shadow keeps the previous answer. Do not retry a slow brief to help the fill: a waiter whose budget is spent starts no load (`40890e4` message) |

`Substrate.brief` in `services/desk-gateway/src/desk_gateway/upstreams.py` POSTs
`{repo, graph_id, surface: grok-bot}` to `/brief` and returns the brief string only.

What `40890e4` added, and what `desk_brief` does with it:

- A compact, state-carrying brief profile for the Grok Bot, shadow by default, plus an
  estimated-spend SLI. Stat: `packages/mcp-server/src/brief-profile.ts`,
  `packages/mcp-server/src/brief.ts`. Desk-task names: `profile` `full|compact`,
  `SUBSTRATE_BRIEF_PROFILE`. The digest does not print those strings and does not name an
  enforce surface list. The desk schema has no `profile`. Do not call a desk brief compact
  or full. A suddenly short brief is unverified, not "nothing is stored".
- A warm own-bank recall snapshot the brief reads from the cache only, off by default. Stat:
  `packages/mcp-server/src/recall-snapshot.ts`. Desk-task flag: `SUBSTRATE_BRIEF_RECALL`.
  Gateway recall still runs inside `core.brief` while that snapshot stays off. An empty
  `substrate.brief` with a populated `recall` is a recall. An empty `recall` with no `reason`
  is unknown, not "no memories".
- A read-only Hindsight inventory, named in the same commit. Stat:
  `packages/mcp-server/src/hindsight-inventory.ts`. Desk-task flag:
  `SUBSTRATE_HINDSIGHT_INVENTORY`. The digest does not print a default for the inventory
  flag. A missing inventory is not an empty bank list. Configured banks past a truncated
  listing are not "missing" (`40890e4` Greptile note).
- A brief too large to cache is composed once, and the fallback text does not carry recall.
  The shadow stale probe does not delay a completed answer. Recall is counted included only
  if it survives the compact byte cap (`40890e4` message). Class-labelled cache counters live
  in `scripts/cache-stats.ts` in that same stat. A seat does not run that script.

Durability. `a735372` (PR #61) puts expiry mode and graph generation into the brief and into
the memory-search cache keys. Stat: `packages/mcp-server/src/brief.ts`,
`packages/mcp-server/src/memory-policy.ts`, `packages/mcp-server/src/index-store.ts`,
`packages/mcp-server/src/mcp.brief.test.ts`. The digest does not name `etag`, `state`,
`surface`, `if_none_match`, or `include_expired`. Do not invent those fields. The gateway
brief is `POST /brief`, so the GET `If-None-Match` cache in `HttpUpstream.request`
(`upstreams.py`) does not apply, and the desk result has no etag. `cached: true` is the
five-minute gateway cache, not HTTP 304. `brief_no_revision_marker` in
`skills/desk-bootstrap/desk-production-loop` still applies. There is no desk argument that
asks recall to show expired rows.

`1e5e719` (PR #62; the same message is also logged as `496878d`) is index export, offline
verify, and restore-to-scratch, a store-free `/livez`, TTL'd `metric_samples`, and a docs
freshness check. Policies ship off or report-only, and the commit deletes no production data.
Stat includes `docs/runbooks/index-archive.md` and `scripts/doctor-runtime.ts`. None of that
is a desk tool. Do not run a restore, a reclaim, or the canary.

`feb597f` (PR #67) is seven opt-in or report-only changes on uplift 5. Defaults keep today's
memory digests, sweep deletes, and the `gate:boot` receipt. Event hashes stay frozen because
the ledger cannot store a new preimage. A hash-version flip still finds the other version's
claim, derived key, and pending review, and a rollback to v1 does the same. Migrate drops
`memory_reviews_hash_idx` on every run, inside the lock, and releases its connection before
the optional table tune. The sweep prints one JSON object and lists lifecycle ids before any
delete. Index-drill errors use the shared redactor. Stat: `packages/mcp-server/src/index-store.ts`,
`packages/mcp-server/src/index-sweep.ts`, `packages/mcp-server/src/memory-write.ts`,
`packages/cli/src/skills.ts`, `scripts/chaos-planes.ts`, `scripts/rehearsal.ts`,
`scripts/release-gate.ts`. The message does not list `skills` subcommands. Do not invent one.
A seat does not migrate, drill, or run that CLI.

`6e0dfd4` (PR #66) added operator-only `skills_approve` and approved-only `skills_list` (one
entry per name), plus `SUBSTRATE_SKILLS_GOVERNANCE=off|report|enforce` (default off; report
warns once; enforce links only approved skills and never unlinks). Stat:
`packages/mcp-server/src/skills/registry.ts`, `packages/mcp-server/src/mcp.ts`,
`packages/projector/src/skills-governance.ts`. Those MCP names are not on
`contracts/tool-rosters/_core.yaml`. Calling them on the desk endpoint is an unknown tool (§1).

`omp-sessions` is not named anywhere in that digest. The desk task records it as a read-only
Hindsight bank: 68 omp session digests, one document per session, tagged by repo and date.
`memory_recall` in `core.py` searches `ctx.seat.memory_own` and, when `include_shared` is
true, `ctx.seat.memory_shared`. It has no bank argument, so it does not search
`omp-sessions`. A miss there is not "no such session". Do not retain into that bank.

---

## Worked example

**Good — INFRA redeploys a Railway service.**

```
desk_railway_status {project: agent-substrate}                    → prior deployment id dpl_7f…
approval obtained via LEAD ↔ Ove 1:1; id apr-2026-09-30-014
desk_railway_redeploy {project: agent-substrate, service: hindsight-api,
  prior_deployment_id: "dpl_7f…", approval_id: "apr-2026-09-30-014",
  rollback_plan: "Redeploy dpl_7f… from the dashboard; under 2 min; no schema change"}
→ ok, new deployment id
Receipt: approvals=[apr-2026-09-30-014], rollback_plan as above, command tail recorded
```

**Bad — ANDROID gets `not_configured` from `desk_play_track_status`.**

```
→ {error: not_configured, reason: "play developer api credential not provided"}
Seat opens the Play Console in the browser with a personal account, reads the track, reports
"rollout at 20%".
```

The number may be right and the receipt cannot prove it: the read is un-audited, the credential
was never the seat's to use, and the claim is unverifiable by re-running the receipt. Correct
response: `unverified: ["Play track state not read — desk_play_track_status not_configured"]`,
and tell LEAD so INFRA can add the credential to the gateway env.

**Bad — WEB gets 403 from `desk_vercel_deployments` and tries `/mcp/systems`.**

The second endpoint is also 403 and now two audit rows show a seat probing another seat's
surface. One 403 is a misconfiguration; the response is `skills/desk-bootstrap` §1, not a search.

---

## Failure modes

| Mode | Symptom | Fix |
|---|---|---|
| Guessed tool name | Unknown-tool error | Read `tools/list`; the roster file names them exactly |
| Empty read taken as "none" | Claim built on a fail-open result | Check for `reason`; move the claim to `unverified` |
| Retry loop on a refusal | Same refusal N times in the audit log | One call, one blocker to LEAD |
| Invented `approval_id` | Schema passes, audit shows an id that matches no approval | PD-5 breach; obtain a real approval |
| Long single call | Empty result, reason names the 20 s deadline | Bound `limit`/`lines`/`timeout_sec`; split |
| 403 explored | Multiple endpoints probed | Stop at the first 403; tell LEAD |
| Browser workaround | Action done outside the gateway after `not_configured` | Record in `unverified`; ask INFRA for the credential |
| Secret in an argument | Redacted args hash, token exposed in transit | Never supply a secret; the gateway holds them |
| Extra argument | Validation error | Schemas are `additionalProperties: false` |
| `profile` or `if_none_match` sent to `desk_brief` | Validation error | Not desk arguments. §7 |
| Short brief read as "nothing known" | `40890e4` adds a shadow-by-default compact profile; the gateway returns the brief string with no profile label | Record it in `unverified`. Do not pass `profile` |
| `skills_approve` or the `skills` CLI from a seat | Unknown tool, or a command `feb597f` does not list | Stop. §7 |

---

## Gate mapping

| Rule | Gate or directive | Why |
|---|---|---|
| `rollback_plan` on g5 tools | G-5 | The gateway refuses without it; the receipt must carry the same plan |
| `approval_id` on g5/g6 tools; echoed into the event | G-6, PD-5 | Approval is recorded in two places that must agree |
| No secrets in arguments | G-3, PD-4 | Arguments are hashed into an audit row and may transit upstreams |
| Roster changes go through contract review | G-4 | Every seat is a consumer of `contracts/tool-rosters/**` |
| Roster count 10–15 (≤ 20 with a pack); g5/g6 tools carry their fields | G-7 | The same band doctor checks at runtime |
| `not_configured` and fail-open reads land in `unverified` | G-2, PD-1, PD-6 | A result you did not get is not a result you can claim |
| Desk brief arguments stay the roster schema | G-4 | Substrate `memory_brief` gained optional fields. The desk tool did not, so a seat must not send them |
