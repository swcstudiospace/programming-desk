---
name: desk-substrate
description: How a desk seat reads substrate brief, durability, and skill-lifecycle behavior through the gateway, without calling substrate tool names.
bots: [all]
gates: [G-2, G-4]
---

# Desk substrate

## When this applies (L1)

Use this when a turn depends on what `desk_brief` actually contains, on whether a memory is still
inside its TTL, or on a skill-lifecycle command (`skills` CLI, migrate, drill, approve). The desk
reaches the substrate only through `desk_*` tools. Substrate MCP names (`memory_brief`,
`memory_search`, `memory_write`, `skills_list`, `skills_approve`) are not desk tools.

```
Need substrate behavior?
│
├─ Start of a turn ──▶ desk_brief. Read substrate and recall as two results. §1
├─ Want profile or if_none_match on that call? ──▶ The desk schema has no such field. §1 §2
├─ Want a fact from memory ──▶ desk_memory_recall. omp-sessions is not one of its banks. §3
├─ Want to keep a fact ──▶ desk_memory_retain. Same evidence rule as skills/hindsight-memory. §3
├─ skills CLI, migrate, drill, skills_approve ──▶ Not a desk call. §4
└─ About to claim the brief was compact, fresh, or a 304 ──▶ The gateway does not say that. §1 §2
```

Tool names on the desk roster are unchanged. `swcstudiospace/agent-substrate` returned GitHub 404
from this seat. Every substrate sentence cites a commit in the history digest of main `feb597f`
(`git log --stat` since 8 Oct 2026). A path is a path that commit's stat lists. The file was not
opened. Where the digest states a behavior and does not print a flag name, the desk task's name
is written beside the SHA. Gateway sentences cite files opened in this repository.

---

## Method (L2)

### §1 Brief pipeline (`40890e4`, PR #64)

| Piece | What `40890e4` states | Seat consequence |
|---|---|---|
| Single-flight | Identical concurrent misses share one load. A waiter whose budget is spent starts no load. Stat: `packages/mcp-server/src/cache.ts` | Do not retry a slow brief to help the fill |
| Stale-while-revalidate | Shadow by default for the brief. The shadow stale probe does not delay a completed answer. Same stat. Desk-task flag: `SUBSTRATE_CACHE_SWR` | Do not set the flag. A shadow answer is the previous brief |
| Brief profile | Compact, state-carrying profile for the Grok Bot, shadow by default, with an estimated-spend SLI. Stat: `packages/mcp-server/src/brief-profile.ts`. Desk-task names: `profile` `full|compact`, `SUBSTRATE_BRIEF_PROFILE`. The digest does not print those strings | `desk_brief` accepts `graph_id`, `task_id`, `refresh` only. Do not call the result compact or full |
| Recall snapshot | Warm own-bank snapshot the brief reads from the cache only, off by default. Stat: `packages/mcp-server/src/recall-snapshot.ts`. Desk-task flag: `SUBSTRATE_BRIEF_RECALL` | Gateway recall still runs. An empty substrate string is not an empty recall |
| Inventory | Read-only Hindsight inventory. Stat: `packages/mcp-server/src/hindsight-inventory.ts`. Desk-task flag: `SUBSTRATE_HINDSIGHT_INVENTORY`. The digest does not print that flag's default. Banks past a truncated listing are not reported missing | A missing inventory is not an empty bank list |
| Oversized brief | Composed once. Fallback text does not carry recall. Same commit message | A short fallback is not the recall you just wrote |

The gateway cache is separate. `brief` in `services/desk-gateway/src/desk_gateway/tools/core.py`
stores a successful result for 300 seconds (`BRIEF_TTL_SEC`) and returns `cached: true`.
`refresh: true` bypasses that cache only. The same function gathers the substrate brief and
`memory_recall`. `Substrate.brief` in `services/desk-gateway/src/desk_gateway/upstreams.py`
POSTs `{repo, graph_id, surface: grok-bot}` and returns the brief string only. Class-labelled
counters are `scripts/cache-stats.ts` in the `40890e4` stat. A seat does not run that script.

### §2 Durability (`a735372` PR #61, `1e5e719` PR #62)

`a735372` puts expiry mode and graph generation into the brief and into the memory-search cache
keys. Stat: `packages/mcp-server/src/brief.ts`, `packages/mcp-server/src/memory-policy.ts`,
`packages/mcp-server/src/index-store.ts`, `packages/mcp-server/src/mcp.brief.test.ts`. The digest
does not name `etag`, `state`, `surface`, `if_none_match`, or `include_expired`. Do not invent
those fields, and do not ask recall to return expired rows. There is no desk argument for that.

The gateway brief is `POST /brief`, so the GET `If-None-Match` path in `HttpUpstream.request`
(`upstreams.py`) does not apply. The desk result has no etag. `cached: true` is the five-minute
gateway cache, not HTTP 304. `brief_no_revision_marker` in
`skills/desk-bootstrap/desk-production-loop` still applies.

`1e5e719` (the same message is also logged as `496878d`) is verified logical export, offline
verify, and restore-to-scratch of the index; a store-free `/livez`; TTL'd `metric_samples`; and
docs freshness. Every policy ships off or report-only. The commit deletes no production data.
Stat includes `docs/runbooks/index-archive.md` and `scripts/doctor-runtime.ts`. A seat does not
run a restore, a reclaim, or the canary.

### §3 Recall sources, including `omp-sessions`

`desk_memory_recall` searches the banks on the seat token (`core.py`: `memory_own`, plus
`memory_shared` when `include_shared` is true). There is no bank argument.

`omp-sessions` is not named in the history digest through `feb597f`. The desk task records it
as a read-only Hindsight bank of omp session digests: one document per session, tagged by repo
and date, 68 documents. This seat did not re-count it. There is no substrate path to cite.

- Do not retain into it. Retain still requires `receipt_path` or `source` and still writes the
  seat bank (`skills/hindsight-memory`).
- A miss in the `pd-*` banks is not evidence that no omp session covered the repo or the date.
- A hit that later arrives inside a brief is a pointer to a repo and a date. Open that repo
  before claiming the digest.

### §4 Skill lifecycle (`6e0dfd4` PR #66, `feb597f` PR #67)

`6e0dfd4` adds operator-only `skills_approve` (authority is checked before the body is read; the
merge check is bound to the library's base branch and to the skill by its proposal branch or by
a change to exactly `<name>/SKILL.md`) and `skills_list` (approved-only, one entry per name).
`SUBSTRATE_SKILLS_GOVERNANCE` is `off|report|enforce`, default off: report warns once, enforce
links only approved skills and never unlinks. Stat: `packages/mcp-server/src/skills/registry.ts`,
`packages/mcp-server/src/mcp.ts`, `packages/projector/src/skills-governance.ts`. Those MCP names
are not on the desk roster. Calling them is an unknown tool (`skills/desk-gateway` §1).

`feb597f` is hash v2, the lifecycle report, the guarded migrate, the drills, and the `skills`
CLI. Defaults keep today's memory digests, sweep deletes, and the `gate:boot` receipt. Event
hashes stay frozen. A hash-version flip still finds the other version's claim, derived key, and
pending review; a rollback to v1 does the same. Migrate drops `memory_reviews_hash_idx` on every
run, inside the lock, and releases its connection before the optional table tune. The sweep
prints one JSON object and lists lifecycle ids before any delete. Index-drill errors use the
shared redactor. Stat: `packages/cli/src/skills.ts`, `packages/mcp-server/src/index-store.ts`,
`packages/mcp-server/src/index-sweep.ts`, `packages/mcp-server/src/memory-write.ts`,
`scripts/chaos-planes.ts`, `scripts/rehearsal.ts`, `scripts/release-gate.ts`. The message does
not list CLI subcommands. Do not invent one, and do not run migrate or a drill from a desk turn.
A skill still enters a seat's default set only by a reviewed pull request,
`scripts/generate-templates.py`, and `skills/pack-sync`.

---

## Failure modes

| Mode | Symptom | Fix |
|---|---|---|
| `profile` or `if_none_match` on `desk_brief` | Validation error | Those fields are not desk arguments |
| Gateway cache confused with substrate SWR | `refresh: true` expected to change a shadow substrate cache | `refresh` bypasses only the gateway's 300 second cache (`core.py`) |
| Empty substrate string read as no recall | Recall snapshot off by default (`40890e4`) while gateway recall ran | Read `recall` on the same `desk_brief` |
| Short brief treated as empty memory | Compact profile is shadow by default (`40890e4`, `packages/mcp-server/src/brief-profile.ts`) | `unverified`. Do not invent `profile` on the desk call |
| Cached brief treated as HTTP 304 | Desk brief is `POST /brief` and returns the string only (`upstreams.py`) | `brief_no_revision_marker` still applies |
| `omp-sessions` written or "not found" | Digest stored in `pd-<seat>`, or a session denied from a `pd-*` miss | Read-only, and not a desk recall bank. §3 |
| `skills_approve` or `skills` CLI from a seat | Unknown tool, or a subcommand `feb597f` does not list | Stop. §4 |

---

## Gate mapping

| Rule | Gate or directive | Why |
|---|---|---|
| Desk tool names and arguments stay the roster schema | G-4 | Substrate fields the gateway does not forward are not desk arguments |
| Unopened substrate files are cited as commit stats | G-2, PD-1 | `40890e4`, `a735372`, `1e5e719`, `6e0dfd4`, and `feb597f` are the source. A stat path is not a file this seat read |
| No migrate, drill, or skill approve from a seat | PD-5 | Those are operator actions in `feb597f` and `6e0dfd4`, not roster tools |
| `omp-sessions` is not a write | PD-2 | The desk task records it as a read-only recall source. The digest does not name a writer |
