---
name: desk-substrate
description: >-
  How Grok Bot reads substrate brief, durability, and skill-lifecycle behavior
  through the seat gateway. Substrate tool names are not called.
---

# Desk substrate

Grok Bot reaches the substrate only through the seat gateway
(`grokbot/skills/desk-shared-memory`). Do not call `memory_brief`, `memory_search`,
`memory_write`, `skills_list`, or `skills_approve`. Do not open Hindsight, RAGFlow, or a
substrate address.

`swcstudiospace/agent-substrate` was not readable (GitHub 404). Substrate sentences cite a
commit in the history digest of main `feb597f` (`git log --stat` since 8 Oct 2026). A path is
a path that commit's stat lists. The file was not opened. Flag names the digest does not print
are marked as the desk task's names.

```
Need substrate behavior?
│
├─ Start of a turn ──▶ desk_brief. Read substrate and recall as two results. §1
├─ profile or if_none_match ──▶ Not arguments of desk_brief. §1 §2
├─ A remembered fact ──▶ desk_memory_recall. omp-sessions is not one of its banks. §3
├─ skills CLI, migrate, drill, skills_approve ──▶ Not a gateway call. §4
└─ About to say the brief was compact or a 304 ──▶ The gateway does not say that. §1 §2
```

## §1 Brief pipeline

`40890e4` (PR #64) is the Grok brief pipeline.

- Identical concurrent misses share one load. A waiter whose budget is spent starts no load.
  Shadow-by-default stale-while-revalidate does not delay a completed answer. Stat:
  `packages/mcp-server/src/cache.ts`. Desk-task flag: `SUBSTRATE_CACHE_SWR`. Do not set it,
  and do not retry a slow `desk_brief` to help the fill.
- Compact, state-carrying brief profile for the Grok Bot, shadow by default, with an
  estimated-spend SLI. Stat: `packages/mcp-server/src/brief-profile.ts`. Desk-task names:
  `profile` `full|compact`, `SUBSTRATE_BRIEF_PROFILE`. The digest does not print those
  strings. `desk_brief` has no `profile` argument. Do not call the result compact or full.
  A suddenly short brief is unverified.
- Warm own-bank recall snapshot, read from the cache only, off by default. Stat:
  `packages/mcp-server/src/recall-snapshot.ts`. Desk-task flag: `SUBSTRATE_BRIEF_RECALL`.
  The gateway still recalls inside `desk_brief`
  (`services/desk-gateway/src/desk_gateway/tools/core.py` gathers both). An empty substrate
  string with a populated `recall` is a recall.
- Read-only Hindsight inventory. Stat: `packages/mcp-server/src/hindsight-inventory.ts`.
  Desk-task flag: `SUBSTRATE_HINDSIGHT_INVENTORY`. The digest does not print that default.
  A missing inventory is not an empty bank list. Banks past a truncated listing are not
  missing.
- A brief too large to cache is composed once, and the fallback text does not carry recall
  (`40890e4` message).

`desk_brief` caches a success for five minutes (`BRIEF_TTL_SEC` 300 in `core.py`).
`refresh: true` skips that gateway cache only. `Substrate.brief` in
`services/desk-gateway/src/desk_gateway/upstreams.py` POSTs
`{repo, graph_id, surface: grok-bot}` and returns the brief string only. Cache counters are
`scripts/cache-stats.ts` in the `40890e4` stat. Do not run that script.

## §2 Durability

`a735372` (PR #61) puts expiry mode and graph generation into the brief and the memory-search
cache keys. Stat: `packages/mcp-server/src/brief.ts`, `packages/mcp-server/src/memory-policy.ts`,
`packages/mcp-server/src/index-store.ts`. The digest does not name `etag`, `if_none_match`, or
`include_expired`. Do not invent them, and do not ask recall for expired rows.

The gateway brief is `POST /brief`, so it does not use the GET `If-None-Match` cache in
`upstreams.py`. The desk result has no etag. `cached: true` is the five-minute gateway cache,
not HTTP 304. `brief_no_revision_marker` still applies.

`1e5e719` (PR #62; also logged as `496878d`) is index export, verify, and restore-to-scratch,
a store-free `/livez`, TTL'd `metric_samples`, and docs freshness. Policies ship off or
report-only. Stat includes `docs/runbooks/index-archive.md`. Do not run a restore, a reclaim,
or the canary.

## §3 `omp-sessions`

The history digest does not name `omp-sessions`. The desk task records it as a read-only
Hindsight bank: 68 omp session digests, one document per session, tagged by repo and date.
This seat did not re-count them. `desk_memory_recall` has no bank argument (`core.py`), so a
miss is not "no omp session". Do not retain into `omp-sessions`. A hit that shows up later
inside a brief is a pointer. Open the repo and the date before claiming the digest.

## §4 Skill lifecycle

`6e0dfd4` (PR #66) adds operator-only `skills_approve` and approved-only `skills_list`, and
`SUBSTRATE_SKILLS_GOVERNANCE=off|report|enforce` (default off; report warns once; enforce
links only approved skills and never unlinks). Stat: `packages/mcp-server/src/skills/registry.ts`,
`packages/projector/src/skills-governance.ts`. Those names are not on the desk endpoint.

`feb597f` (PR #67) keeps today's memory digests, sweep deletes, and the `gate:boot` receipt
unless an operator opts in. Event hashes stay frozen. A hash-version flip still finds the
other version's claim, derived key, and pending review. Migrate drops `memory_reviews_hash_idx`
on every run, inside the lock. The sweep lists lifecycle ids before any delete. Index-drill
errors use the shared redactor. Stat: `packages/cli/src/skills.ts`,
`packages/mcp-server/src/index-store.ts`, `packages/mcp-server/src/memory-write.ts`,
`scripts/chaos-planes.ts`. The message does not list `skills` subcommands. Do not invent one,
and do not migrate or drill.
