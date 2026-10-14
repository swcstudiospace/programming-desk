---
name: desk-shared-memory
description: Seat memory, documents, events, ownership, receipts and doctor, reached only through the desk gateway.
bots: [all]
gates: [G-2, G-3, G-4]
---

# Desk shared memory

A seat reaches memory, documents, events, ownership and receipts only by calling its desk-gateway
MCP endpoint. The public gateway is `https://desk.swcstudio.space` and the seat connector is
`https://desk.swcstudio.space/mcp/<seat>`. Do not open Hindsight, RAGFlow, a substrate loopback
address, or any `railway.internal` host. The gateway holds those upstreams.

The names below are the eight tools in `contracts/tool-rosters/_core.yaml`. A tool that is not on
the seat's `tools/list` does not exist. Do not call the substrate names the gateway uses
internally (`memory_search`, `memory_write`, `docs_search`, `skills_list`, `skills_approve`).

```
Need desk context?
│
├─ Start of a turn ──▶ desk_brief. §1
├─ A fact you might already know ──▶ desk_memory_recall. Treat the hit as unverified. §2
├─ A decision, command, environment fact or gotcha you can point at ──▶ desk_memory_retain. §3
├─ A document, not a memory ──▶ desk_docs_search, then open the file. §4
├─ A milestone worth the event log ──▶ desk_event_emit. §5
├─ About to edit ──▶ desk_ownership_resolve first. §6
├─ About to claim done ──▶ desk_receipt_check. §7
└─ Integrity of this seat ──▶ desk_doctor. §8
```

A read that returns `not_configured`, or an `error` with a `reason`, is unverified. Name the tool
and the reason, and continue by opening the file. Do not retry the upstream yourself. A `403`
means the wrong seat endpoint: stop.

A write that returns an error did not reach its upstream. `desk_event_emit` still saves a local
copy first: a rejected send comes back as an error with `local_mirror: true`. That local line is
already stored. Do not retry it. For any other write, retry once only when the reason is
transient and the result has no `local_mirror`. A refusal such as `evidence_required`,
`secret_refused`, `invalid_args`, `forbidden` or `payload_too_large` is not transient.

Never put a token, passphrase, tailnet name or `railway.internal` host in an argument.

`swcstudiospace/agent-substrate` was not readable from this seat. Substrate sentences cite a
commit in the history digest of main `feb597f`. A path is a path that commit's stat lists. The
file was not opened.

## §1 desk_brief

Call it at the start of a turn. Optional arguments are `graph_id`, `task_id` and `refresh`.
There is no `profile` and no `if_none_match`. The gateway caches a successful brief for five
minutes (`services/desk-gateway/src/desk_gateway/tools/core.py`, `BRIEF_TTL_SEC` 300) and marks
a hit `cached: true`. `refresh: true` skips that cache only. The same function gathers the
substrate brief and a recall, so an empty substrate string is not an empty recall. An upstream
`error` inside the result is still a failed lookup. An empty recall with no `reason` is unknown,
not "nothing is stored".

`40890e4` (PR #64) is the substrate side. Identical concurrent misses share one load
(`packages/mcp-server/src/cache.ts`). Stale-while-revalidate for the brief is shadow by default;
the desk task names the flag `SUBSTRATE_CACHE_SWR`. A compact profile for the Grok Bot is also
shadow by default (`packages/mcp-server/src/brief-profile.ts`; desk-task names `profile`
`full|compact` and `SUBSTRATE_BRIEF_PROFILE`). An own-bank recall snapshot is off by default
(`packages/mcp-server/src/recall-snapshot.ts`; desk-task flag `SUBSTRATE_BRIEF_RECALL`). A
read-only Hindsight inventory is in the same commit
(`packages/mcp-server/src/hindsight-inventory.ts`; desk-task flag
`SUBSTRATE_HINDSIGHT_INVENTORY`). Do not set those flags. Do not describe the desk brief as
compact, full, or HTTP 304. `Substrate.brief`
(`services/desk-gateway/src/desk_gateway/upstreams.py`) POSTs `/brief` and returns the brief
string only, so the result has no etag.

`a735372` (PR #61) puts expiry mode and graph generation into the brief and the memory-search
cache keys (`packages/mcp-server/src/memory-policy.ts`). The digest does not name an expired-row
argument. Do not ask for one. Longer notes are `skills/desk-substrate`.

## §2 desk_memory_recall

`query` is required. `limit` defaults to 8. `include_shared` defaults to true. The gateway
chooses the banks from the seat token. There is no bank argument.

Recall is a hint about where to look. Re-open the file or re-run the command before stating the
fact.

`omp-sessions` is a read-only Hindsight bank the desk task records as 68 omp session digests,
one document per session, tagged by repo and date. The history digest through `feb597f` does not
name the bank, so there is no substrate path to cite. This recall does not search it. A miss is
not "no such session". Do not retain into it.

## §3 desk_memory_retain

`content` is required, 8 to 8000 characters. The call is refused without `receipt_path` or
`source`, and refused when `content` contains a credential shape. `receipt_path` matches
`.receipts/bot-0N-<seat>/<file>.json`. `source` is a URL.

Retain a decision, a verified command, an environment fact or a gotcha. Do not retain a
transcript, a secret, another seat's work, or an omp session digest. The gateway writes the
seat's own bank. `feb597f` (PR #67, stat `packages/mcp-server/src/memory-write.ts`) keeps today's
memory digests unless an operator opts in. That does not add a desk argument. Do not run the
`skills` CLI, the guarded migrate, or a drill (`packages/cli/src/skills.ts`,
`packages/mcp-server/src/index-store.ts` in that stat). `6e0dfd4` (PR #66) adds `skills_list`
and `skills_approve`; they are not on this endpoint.

## §4 desk_docs_search

`query` is required. Pass `repo` as `owner/name` when the question is about that repo. `limit`
defaults to 8. A chunk is not a repository fact until the file it names is opened. An empty
result with a `reason` is a failed search.

## §5 desk_event_emit

`kind` is required. Pass `graph_id` and `task_id` when the turn has them. `payload` is an object,
capped at 4 KB, and redacted. An error with `local_mirror: true` means the local audit line is
saved and the upstream did not accept the event. Do not send the same milestone again.

## §6 desk_ownership_resolve

`paths` is required. Run it before the first edit. The last matching rule in `ownership.yaml`
wins. Do not edit an unowned path or a path whose `owner` is another seat.

## §7 desk_receipt_check

`bot` is required. Pass `receipt` or `receipt_path`. `strict` defaults to true. The gateway runs
G-2, G-3, G-5 and G-6 against that receipt and writes nothing to git.

## §8 desk_doctor

`action` is one of `check`, `register`, `install_prompt`, `repair`. `repair` re-runs
`install_prompt`. It does not edit a gate, a receipt, or another seat's files. A red row is
information. Report it.
