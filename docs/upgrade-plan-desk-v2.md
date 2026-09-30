# Programming Desk v2 — Upgrade Plan

**Authored:** 2026-09-30 (Sydney), by Ove through Claude (Cowork). This is an operator proposal, not a seat receipt.  
**Status:** Proposal on a draft PR. Nothing in this document has been built, deployed or verified. Every runtime claim below is a target state unless the line says "today".  
**Audience:** LEAD (intake and kickoff), QUALITY (contract and gate review), the five build seats (owned-path work), Ove (approvals).  
**Companion PR:** `swcstudiospace/agent-substrate` — `docs/data-planes.md`, `docs/railway-tailscale.md`, `.env.example`, README/PROJECT data sections.  
**Decisions locked with Ove on 2026-09-30:** see §3.

Policy this plan stays inside: `docs/gotxcot-cloud-pipeline.md` (5–8 nodes, 4–8 steps, two uplifts), `docs/github-sot-orchestration.md` (GitHub is the record), `docs/desk-operating-model.md` (Ove ↔ LEAD 1:1, QUALITY off-channel), `docs/quality-gates.md` (G-1…G-6), `ownership.yaml` (last match wins, unowned fails). The plan adds surfaces; it does not weaken a gate.

---

## 1. ORIGINAL (operator ask, verbatim)

> We're upgrading our Programming Desk application in https://github.com/swcstudiospace/programming-desk We want each bot to have it's own unique interface which connects our Railway resources properly via Tailscale. So we have 2 projects in Railway. Ultrathink which has our databases and then we have Agent Substrate which has 2 applications "Hingsight" and "RAGflow" so please upgrade our Agent Substrate documents to use the 3 databases and 2 applications intelligently then wire them into our Programming Desk whilst doing an overall uplift to our Programming Desk as a whole. We want a Grok Bot share which will integrate the entire desk from Add Bot and ensure our XML's Skills, Memories, Tools etc are still integrated properly. We want to drive the application from outside of the Desk speaking only to Lead. All of our Bots require 10-15 proper tools for themselves. Please introduce proper integrations of the applications and stuff from Grok Bot leveraging other skills and stuff made by other Teams. For our actual ios and Android bots can load up specialised tools for applications etc. Please plan an upgrade

LEAD's first uplift takes this block as `ORIGINAL`. Do not paraphrase it.

---

## 2. What is true today (inventory, with where it was read)

| Area | State today | Read from |
|---|---|---|
| Seats | Seven Grok Bots. Desk group `4d78b294-5b65-46a9-bec9-86cdbc54aa3e` holds LEAD + SYSTEMS, WEB, ANDROID, IOS, INFRA (platform max six). QUALITY is off-channel. | `prompts/bot-00-programming-lead.xml`, `docs/desk-operating-model.md` |
| Prompts | `prompts/_shared/core-directives.xml` + `prompts/bot-0N-*.xml` → `scripts/assemble-prompts.sh` → `prompts-assembled/<SEAT>.xml`. Runtime loads `SYSTEM_PROMPT.xml` under `/home/box/agent-data/agents/<uuid>/` on the Bot computer. Channel id and all seven agent UUIDs are **hardcoded** in the sources. | `ARCHITECTURE.md` §7, prompt sources |
| Skills | 17 skills under `skills/` (L1/L2/L3). Each seat's prompt lists `load="always"` skills. No Grok Bot private-skills or Marketplace packaging exists. | `skills/README.md` |
| Tools | Grok host tools (computer, files, browser, `SendToAgent`/`SendToUser`) plus connectors named in docs: Linear MCP, Notion, `user-greptile`, `user-hermes-agent` (`agent_bus_*`). No per-seat tool roster, no contract for tools. | `docs/github-sot-orchestration.md` §4–5 |
| Gates | G-1…G-6 in `ci/gates/`, 90 tests. `ci/.github/workflows/gates.yml` exists but there is **no** `.github/` at the repo root, so the workflow is not active on PRs. Greptile reviews PRs. | tree listing, `README.md` |
| Spikes | Tier-1 unified LSP broker (`infra/unified-lsp-broker/`, INFRA) and `web/mcp-unified-lsp/` stdio adapter (WEB). Boundary in `broker_mcp_boundary.yaml`; not yet a `contracts/` surface. | PR #10, #11 |
| Substrate | `substrate-mcp` on the VPS at `127.0.0.1:7410` (streamable HTTP `/mcp` + `POST /brief`, `POST /events`). 13 tools: `memory_brief`, `memory_write`, `memory_search`, `events_emit`, `skills_propose`, `desktop_run`, `graph_get`, `issue_get`, `graph_find`, `graph_register`, `graph_claim`, `graph_release`, `graph_complete`. Per-surface bearer tokens incl. `SUBSTRATE_TOKEN_GROK_BOT`. | `~/src/repos/agent-substrate/packages/mcp-server/src/mcp.ts`, `.env.example` |
| Substrate data | GreptimeDB reached on its **public** Railway domain; TimescaleDB via the **public TCP proxy** `monorail.proxy.rlwy.net:49679` (the env comment says `*.railway.internal` does not resolve from the VPS). RAGFlow: Phase 5 docs half owner-skipped. Memory recall: Phase 7 planned against Agentmemory and skipped; Claude Code still carries a local `hindsight` stdio MCP. Dragonfly: Phase 8 pending. | `/etc/substrate/substrate.env` (hosts only), `.planning/STATE.md`, `v1.0-MILESTONE-AUDIT.md` |
| Railway | Two projects in Ove's Railway account (not visible from this session's Railway connection): **Ultrathink** = GreptimeDB, TimescaleDB, DragonflyDB; **Agent Substrate** = Hindsight (`hindsight-api` REST + MCP on 8888, `hindsight-ui`, own pg17+pgvector), RAGFlow. Confirmed by Ove 2026-09-30. | Ove; Railway template pages |
| Tailnet | `vps` 100.90.229.45, `grok-bot-box` 100.94.38.2, `oves-mac-mini` 100.80.62.2, `ove-xps-15` 100.104.90.39, `railway-app` 100.77.7.42 (online; which Railway project it lives in is not known from here). | `tailscale status` on the VPS |
| Shared skills | `/root/agent-skills` = read-only checkout of `swcstudiospace/agent-skills`, projected to Claude Code, Grok Build, Cursor, Muse and Hermes by `substrate-skills-sync`. **No Grok Bot projection.** Proposals only via `skills_propose` PRs. | `/root/agent-skills/README.md` |
| Grok Bot → VPS | `grok-hermes-connector` (OAuth, redactor, audit) is the current Lane C path; `grok-claude-cloud-connector` at `claude.swcstudio.space` (`127.0.0.1:8789`) shows the OAuth + `x-connector-key` pattern Grok Bot's **Add MCP Server** card accepts. | `~/src/repos/grok-claude-cloud-connector/docs/grok-bot-setup.md` |
| Grok Bot platform | Group chats hold 2–6 Bots. Skills live in one account-wide **private skills** library (`/` in the composer; Marketplace → Your plugins → Manage plugins and skills). Connectors and packaged skills install account-wide from **Marketplace**; per-plugin tools can be enabled or disabled. Routines: 50 per Bot, event triggers via Cursor integrations (GitHub, Slack). **Share → Create template** (Public or Team-only) copies profile, settings, enabled skills, routines and avatar — not memory, history, credentials, computer or group membership. Networking: **Route egress through this desktop** (per desktop) or Enterprise **Team Setup** manifests for Tailscale; otherwise egress is Cursor's shared IPs. Mobile: iOS 18+, Android 9+; advanced Bot configuration is desktop-only. | docs.x.ai/grok-bot (bots, chat-and-collaboration, skills-routines-and-automations, settings-and-notifications, private-networks, mobile, faq) |

Everything in this table was opened or run on 2026-09-30. Anything not in it is an assumption and appears in §13.

---

## 3. Decisions (locked with Ove, 2026-09-30)

| Id | Decision | Consequence |
|---|---|---|
| **D-1** | Ultrathink = GreptimeDB + TimescaleDB + DragonflyDB. Agent Substrate = Hindsight + RAGFlow. | §6 data-plane policy is written against exactly these five services. Agentmemory (substrate Phase 7) is replaced by Hindsight. |
| **D-2** | Bots reach Railway through a **Desk Gateway on the VPS**, not by joining the tailnet. Railway services are reached from the VPS over Tailscale Forwarders inside each Railway project. | Bots hold no database credentials. Public TCP proxies and public DB domains are retired after cutover (§5). |
| **D-3** | Grok Bot share = **seven Team-only templates** (one per seat) + a `desk-bootstrap` skill that recreates group, connector and prompt, and a `desk-doctor` that proves it. | Templates carry no secrets, no internal URLs beyond the public gateway host, no UUIDs (§9). |
| **D-4** | Plan lands as a draft PR here plus a shareable document; agent-substrate doc upgrades land as a companion draft PR. | No merge, no tracker rows, no deploys from this authoring session. |

---

## 4. Target architecture

```
  Ove (desktop / iOS / Android)      Slack · GitHub · other desks · cron
              │ 1:1                              │ POST /v1/intake (origin token)
              ▼                                  ▼
         ┌─────────┐   desk-intake-poll routine ┌────────────────────────┐
         │  LEAD   │◀───────────────────────────│  Desk Gateway (VPS)    │
         └────┬────┘   desk_intake_next/ack     │  desk.swcstudio.space  │
   tickets    │ SendToAgent 1:1                 │  nginx TLS → :8791     │
              ▼                                 │  OAuth · per-seat MCP  │
 ┌──────────────────────────────────────┐       │  /mcp/lead  /mcp/web … │
 │ Programming Desk group (max 6)       │──────▶│  10–15 tools per seat  │
 │ LEAD SYSTEMS WEB ANDROID IOS INFRA   │ HTTPS │  tool packs (ios/andr) │
 └──────────────────────────────────────┘       └───────────┬────────────┘
      QUALITY (off-channel) ── /mcp/quality ────────────────┤
                                                            │ loopback
                                          ┌─────────────────┴──────────────┐
                                          │ substrate-mcp :7410 · agent-bus │
                                          │ :8790 · claude-cloud :8789      │
                                          └─────────────────┬──────────────┘
                                                            │ tailnet (MagicDNS)
                 ┌──────────────────────────────────────────┴───────────────────────────┐
                 │ Railway · Ultrathink (production)      Railway · Agent Substrate       │
                 │ tailscale-forwarder ──▶ greptimedb     tailscale-forwarder ──▶ hindsight-api
                 │                    ──▶ timescaledb                          ──▶ ragflow
                 │                    ──▶ dragonfly                                      │
                 └────────────────────────────────────────────────────────────────────────┘
```

Four rules hold the picture together:

1. **Only LEAD is addressable from outside.** Humans, other desks, Slack, GitHub and cron reach the desk through LEAD's 1:1 or the gateway intake queue that only LEAD's endpoint can drain (§10).
2. **Each seat has its own interface.** `/mcp/<seat>` returns a different `tools/list`, authenticated by a seat-scoped OAuth client. That list is a contract under `contracts/tool-rosters/` (§7).
3. **Credentials stop on the VPS.** Hindsight, RAGFlow, Greptime, Timescale and Dragonfly credentials stay in `/etc/substrate/substrate.env` and are used by `substrate-mcp`; the gateway reaches those planes over loopback through the substrate and holds only its own upstream tokens (Railway API, Vercel, Play, App Store Connect, Greptile, agent bus) in `/etc/desk-gateway/gateway.env`. A Bot never sees any of them; a template never carries them.
4. **GitHub stays the record.** Tool calls are audited to Greptime, indexed and queued in Timescale, cached in Dragonfly, remembered in Hindsight, searchable in RAGFlow — none of those is a source of truth for what shipped.

---

## 5. Workstream A — Railway over Tailscale (INFRA)

**Goal.** The VPS, and only the VPS (plus Ove's Mac mini for administration), reaches the five Railway services over the tailnet by MagicDNS name. Public TCP proxies and public database domains go away.

**Mechanism.** Railway's private network is per project and per environment (`fd12::/16`, `*.railway.internal`); services in different projects cannot see each other, so one forwarder per project is required. Railway's supported pattern is the **Tailscale Forwarder** template (it replaced the deprecated subnet-router template), configured with `TS_AUTHKEY` and `CONNECTION_MAPPING_n = <src_port>:<service>.railway.internal:<port>`, with a volume for machine identity. The machine name derives from `<project>-<environment>-<service>`.

| Project | Forwarder machine (expected) | Mappings (service names to confirm in n1) |
|---|---|---|
| Ultrathink / production | `ultrathink-production-tailscale-forwarder` | `4000:greptimedb.railway.internal:4000` (HTTP SQL), `4001:…:4001` (gRPC), `4003:…:4003` (Postgres wire), `5432:timescaledb.railway.internal:5432`, `6379:dragonfly.railway.internal:6379` |
| Agent Substrate / production | `agent-substrate-production-tailscale-forwarder` | `8888:hindsight-api.railway.internal:8888` (REST + `/mcp/<bank>/`), `9380:ragflow.railway.internal:9380` (API), `80:ragflow.railway.internal:80` (web, optional) |

**Tailscale ACL (tags).** `tag:railway-forwarder` (both forwarders), `tag:vps` (187.77.130.10), `tag:admin` (Ove's Mac mini, XPS). Grants: `tag:vps` → `tag:railway-forwarder:*` on the mapped ports; `tag:admin` → same; nothing else. Key expiry disabled on the forwarders; auth key reusable, tagged, ephemeral off.

**VPS cutover** (`/etc/substrate/substrate.env` and the new `/etc/desk-gateway/gateway.env`): `GREPTIME_URL=http://ultrathink-production-tailscale-forwarder:4000`, `SUBSTRATE_PG_URL=postgresql://…@ultrathink-production-tailscale-forwarder:5432/railway`, `DRAGONFLY_URL=redis://…@ultrathink-production-tailscale-forwarder:6379`, `HINDSIGHT_URL=http://agent-substrate-production-tailscale-forwarder:8888`, `RAGFLOW_URL=http://agent-substrate-production-tailscale-forwarder:9380`. Traffic inside the tailnet is WireGuard-encrypted, so plaintext service ports are acceptable on the forwarder hop; Hindsight and RAGFlow still require their bearer keys.

**Retire public exposure** (G-6: access change; approval recorded in the INFRA receipt): delete the TimescaleDB TCP proxy; remove the Greptime public domain; keep `hindsight-ui` behind its access key on a Railway domain only if Ove wants browser access without the tailnet, otherwise reach it via the Mac mini. Rollback: re-create the TCP proxy / domain (minutes; no data implication).

**`railway-app` node.** Identify which project it belongs to and what it advertises. If it is the deprecated subnet router or an exit node, retire it after the forwarders are verified. If it already is a forwarder, adopt it and skip the duplicate.

**Bot computers.** They do **not** join the tailnet. They reach `https://desk.swcstudio.space` over normal egress. If the Cursor team uses "Team allowlist only", add `desk.swcstudio.space`. "Route egress through this desktop" on the Mac mini stays documented as an emergency path for INFRA only (it makes the Bot depend on the Mac mini being awake).

**Evidence INFRA records:** `tailscale status` showing both forwarders; `psql`/`curl` from the VPS to each mapped port over the tailnet name; `railway` CLI or dashboard screenshot of the proxy/domain removal; a receipt with the rollback plan.

---

## 6. Workstream B — Substrate data planes (SYSTEMS, agent-substrate repo)

The substrate already defines four planes (runtime, memory, skills, ledger). This workstream binds each plane to exactly one Railway service and states what goes where. The full text lives in the companion PR (`agent-substrate/docs/data-planes.md`); this is the policy the desk depends on.

| Data class | Store | Why this store | Writer | TTL / retention | Not allowed |
|---|---|---|---|---|---|
| Events: every gateway tool call, receipt written, dispatch, intake, seat heartbeat | **GreptimeDB** `agent_events` (append-only, `hash`/`prev` chain; hourly Merkle root anchored to Solana devnet by `packages/ledger`) | Time-series, cheap appends, SQL over HTTP, already the ledger | gateway (`events_emit`), substrate collectors | 180 days hot, then export | Payloads with secrets (redactor runs first), full transcripts |
| Index and coordination: `graph_index`, `graph_nodes`, `graph_steps`, `desk_intake` (the intake queue, drained with `FOR UPDATE SKIP LOCKED`), `desk_claims` (per-Graph-ID claim rows with expiry), `desk_idempotency` (the 30-day processed-key set from `docs/handoff-contracts.md`), `desk_receipts`, `seat_roster`, `tool_pack_state`; hypertables `seat_heartbeat`, `tool_calls_1m` + continuous aggregates | **TimescaleDB** | Relational + hypertables; transactional, so queue, claims and idempotency of record live here; rebuildable from GitHub/Linear/Notion except the queue, which is small | substrate-mcp, gateway | Rows live while the Graph ID is open + 90 days; aggregates 1 year | Being treated as source of truth for what shipped; secrets |
| Cache only: brief cache, `docs_search` and `recall` result cache, per-seat rate-limit counters, a short-TTL mirror of idempotency keys for fast rejects | **DragonflyDB** | Redis-compatible, TTL-native, fast. The substrate owner decision of 2026-09-26 stands: Dragonfly is a caching layer, not a session store, queue or pub/sub; every read falls through to its source when Dragonfly is unreachable | gateway, substrate-mcp | Brief 5 min; search/recall 10 min; counters 1 h; key mirror 24 h | Anything that cannot be lost on restart; queues; locks |
| Memory: decisions, verified commands, environment facts, gotchas, per-seat working preferences; nightly `reflect` into mental models | **Hindsight** banks `pd-desk` (shared; LEAD and QUALITY write, all read), `pd-<seat>` (owner writes), `pd-lead-reports` | retain/recall/reflect with semantic + BM25 + entity + temporal recall; MCP at `/mcp/<bank>/`; replaces Agentmemory (Phase 7) and the local Claude Code `hindsight` stdio server; Hermes `memory.provider` → none | `substrate-mcp` only (`memory_write` → retain, `memory_search` → recall; it holds the tenant key); the gateway calls the substrate | Retain forever; `reflect` weekly prunes into mental models | Unverified claims (retain requires a receipt path or a `source:` URL), secrets (D-04 redactor), other seats' banks |
| Documents: repo docs, skills, contracts, ADRs, product docs for KanbanOS / Desk Lanes / ClippyOS / Auctioning | **RAGFlow** datasets `programming-desk`, `agent-substrate`, one per product repo | Chunked retrieval with headings; API on 9380; embedding TEI `bge-small` as already planned; no chat model needed | ingest job on merge to `main` (GitHub Action → gateway `POST /v1/docs/ingest`) | Re-ingest on merge; dataset versions keep last 5 | Secrets, receipts (they are evidence, not docs), transcripts |

Substrate repo changes (companion PR): `README.md` data line; `.planning/PROJECT.md` "Data" section; `.env.example` (`HINDSIGHT_URL`, `HINDSIGHT_API_KEY`, `HINDSIGHT_BANK_PREFIX`, `DRAGONFLY_URL`, `SUBSTRATE_TOKEN_DESK_GATEWAY`; `AGENTMEMORY_*` removed; tailnet hosts); new `docs/data-planes.md` and `docs/railway-tailscale.md`. `.planning/ROADMAP.md` is not hand-edited: Phase 5 (RAGFlow over the tailnet, docs half un-skipped), Phase 7 (Hindsight, not Agentmemory) and Phase 8 (Dragonfly, cache only) are re-planned with the GSD tooling against `docs/data-planes.md`. Code follows the docs in those phases, not in this desk PR.

---

## 7. Workstream C — Desk Gateway: one interface per seat (SYSTEMS builds, INFRA deploys, QUALITY holds the contract)

### 7.1 Shape

| Item | Value |
|---|---|
| Code | `services/desk-gateway/` (Python, FastAPI; reuse the OAuth AS, PKCE consent page and `x-connector-key` mapping from `grok-claude-cloud-connector`; reuse the substrate `redact()` patterns) — owner SYSTEMS |
| Deploy | `infra/desk-gateway/` (systemd unit, nginx vhost, env template without values) — owner INFRA. Bind `127.0.0.1:8791` (8787, 8789, 8790 are taken). Public host `desk.swcstudio.space → 187.77.130.10`, TLS by the existing cert flow |
| Auth | One OAuth client per seat (`desk-lead`, `desk-systems`, …, `desk-quality`) with scope `seat:<name>`. Grok Bot connects each Bot with **Add MCP Server** → `https://desk.swcstudio.space/mcp/<seat>` → OAuth. Tokens 24 h, refresh 30 d (same as the claude-cloud connector). Header key path kept for smoke tests only |
| Per-seat surface | `tools/list` on `/mcp/<seat>` returns that seat's roster and nothing else. A token for seat A on `/mcp/<seat B>` is 403 |
| Contract | `contracts/tool-rosters/<seat>.yaml` (QUALITY, `contract_surface: true`) — tool name, JSON schema, backend, gate tags (`g5`, `g6`, `read_only`), consumers. `contracts/tool-packs/<app>.yaml` for §7.4. Breaking changes follow G-4 with the seat as consumer |
| Upstreams | substrate-mcp `127.0.0.1:7410`; vps-agent-bus `127.0.0.1:8790`; claude-cloud connector `127.0.0.1:8789`; tailnet forwarders (§5); GitHub via `gh`; Railway API; Vercel API; Google Play Developer API; App Store Connect API; Greptile API |
| Audit | Every call → Greptime `agent_events` (`surface=grok-bot`, `seat`, `tool`, `graph_id`, `task_id`, `ok`, `ms`, redacted args hash). Every G-5/G-6 tool requires `approval_id` and `rollback_plan` in the call and echoes them into the event |
| Failure | Fail open for reads (empty result + `reason`), fail closed for writes and gated tools. 20 s per-call deadline (under the MCP client deadline the LSP spike measured). No upstream stack traces to the Bot |

### 7.2 Shared core (on every seat's endpoint) — 8 tools

| Tool | Backend | Notes |
|---|---|---|
| `desk_brief` | substrate `memory_brief` (which recalls `pd-<seat>` and `pd-desk` from Hindsight) + open tickets for the seat from the index | Called at turn start; cached 5 min in Dragonfly |
| `desk_docs_search` | substrate `docs_search` → RAGFlow over `programming-desk`, `agent-substrate`, and the repo named in the ticket | Read only |
| `desk_memory_retain` | substrate `memory_write` → Hindsight `retain` into `pd-<seat>`; tags `graph_id`, `task_id`, `receipt_path` | Refused without `receipt_path` or `source` |
| `desk_memory_recall` | substrate `memory_search` → Hindsight `recall` over `pd-<seat>` + `pd-desk` (+ `pd-lead-reports` for LEAD) | Read only |
| `desk_ownership_resolve` | `ownership.yaml` at `origin/main` | The G-1 pre-check every seat should run before an edit |
| `desk_receipt_check` | Runs `check_receipt.py`, `check_secrets.py`, `check_rollback.py` on a receipt JSON | Compute only; writes nothing to git |
| `desk_event_emit` | substrate `events_emit` | Seat-attributed |
| `desk_doctor` | `action: check \| register \| install_prompt \| repair` — see §9.3 | The integrity tool |

### 7.3 Seat rosters (core 8 + seat tools)

**LEAD — 15.** `desk_intake_next` (pull the next external work order from `desk_intake`, claiming the row), `desk_intake_ack` (accept / reject / progress → posts back to the origin with Graph ID and links), `desk_graph_register` (substrate `graph_register`, idempotent on Graph ID), `desk_graph_state` (`claim | release | complete`, mirrors Linear and the Notion Issue row through substrate), `desk_bus_start_job`, `desk_bus_wait_job` (Lane B through the agent bus; `handoff_to_hermes` stays the Hermes-only fallback), `desk_roster_status` (seat registration, heartbeats, tool counts, last doctor result). Cursor Cloud Agent launch stays on Grok Bot's native Cursor card; Claude cloud sessions stay on the `claude-cloud` connector.

**SYSTEMS — 14.** `desk_index_query` (Timescale, read-only views), `desk_events_query` (Greptime SQL, bounded, read-only), `desk_cache` (Dragonfly `get | set | del` in the `systems:` namespace, TTL ≤ 24 h, cache semantics only), `desk_lsp_diagnostics` (unified LSP broker; `python`, `go`, `tsjs` are Tier-1, `rust` returns `language_not_tier1` until Tier-2 lands), `desk_contract_propose` (opens a contract-change PR skeleton under `contracts/` from a proposal payload; QUALITY merges), `desk_design_artifact_get` (`design/**` tokens and specs from `origin/main`).

**WEB — 15.** `desk_lsp_diagnostics` (tsjs), `desk_vercel_deployments` (list / get, project-scoped), `desk_vercel_promote` (**g5**: `rollback_plan` + `approval_id`), `desk_vercel_rollback`, `desk_preview_check` (fetch a preview URL, record status + screenshot hash as evidence), `desk_bundle_secret_scan` (G-3 over build output), `desk_contract_ack`.

**ANDROID — 15.** `desk_play_track_status` (Play Developer API, read), `desk_play_staged_rollout` (**g5 g6**: percent, halt threshold, `approval_id`), `desk_play_halt_rollout`, `desk_artifact_size_delta` (APK/AAB before/after), `desk_lint_baseline_diff`, `desk_contract_ack`, `desk_app_tools_load` (§7.4).

**IOS — 15.** `desk_testflight_status` (App Store Connect API, read), `desk_appstore_phased_release` (**g5 g6**), `desk_appstore_pause_release`, `desk_entitlements_diff` (Info.plist + entitlements between two refs), `desk_review_risk_check` (the `app_review_checklist` from the IOS prompt, evaluated against the diff), `desk_contract_ack`, `desk_app_tools_load` (§7.4).

**INFRA — 15.** `desk_railway_status` (both projects: services, latest deployment, health), `desk_railway_logs` (bounded, redacted), `desk_railway_variable_names` (names only, never values), `desk_railway_redeploy` (**g5**: prior deployment id as rollback), `desk_tailscale_status` (forwarders online, mapped ports reachable, ACL self-check), `desk_vps_units` (systemd status of `substrate-*`, `desk-gateway`, `vps-agent-bus`, `grok-claude-cloud`), `desk_db_health` (Greptime, Timescale, Dragonfly, Hindsight `/health`, RAGFlow over the tailnet).

**QUALITY — 15.** `desk_gates_run` (`ci/gates/run_all.py` against a PR ref in a scratch clone, including `--validate-manifest`), `desk_greptile_review` (`trigger | get | comments`), `desk_receipt_approve` (stamps `approved_by` on a receipt in the PR branch; refuses when the receipt's `bot` is `bot-06-quality-security`), `desk_waiver_record` (Greptile waiver receipt), `desk_contract_ack_status` (G-4 acks vs `contract_consumers`), `desk_supply_chain_check` (licence + CVE over lockfile diffs), `desk_secret_scan` (`check_secrets.py` over a ref).

Grok host tools and Marketplace connectors (Linear, Notion, GitHub, Slack, Greptile) sit outside these counts. The 10–15 band is enforced by the new gate in §11.

### 7.4 Tool packs for the mobile seats (and WEB when a product needs it)

A pack is a named, contract-defined bundle of at most five application-specific tools that a seat loads for the life of one ticket. `contracts/tool-packs/<app>.yaml` declares the tools; the gateway implements them; `desk_app_tools_load(app, task_id)` turns them on and `desk_app_tools_load(app, task_id, unload=true)` turns them off. Live tools per seat never exceed 20.

| Pack | Example tools | Backend |
|---|---|---|
| `kanbanos` | `kanbanos_api_smoke`, `kanbanos_supabase_query` (read-only, project-scoped), `kanbanos_push_test` (FCM/APNs to a test device), `kanbanos_feature_flags`, `kanbanos_crash_reports` | KanbanOS API, its Supabase project, FCM/APNs, Sentry/Crashlytics |
| `desklanes` | `desklanes_api_smoke`, `desklanes_scoreboard_get`, `desklanes_push_test`, `desklanes_store_listing_get`, `desklanes_crash_reports` | desklanes API, store listings |
| `clippyos` | `clippyos_api_smoke`, `clippyos_render_job_status`, `clippyos_push_test`, `clippyos_crash_reports` | ClippyOS API |

Delivery mechanism: the gateway emits MCP `notifications/tools/list_changed` after a load. Whether Grok Bot's MCP client honours that notification is **unverified** (§13). Fallback that needs no client support: each pack is also served at `/mcp/<seat>/packs/<app>` and added as a second connector on the seat; the Bot enables or disables it per ticket from Marketplace → Your plugins, where per-plugin tools can be toggled.

### 7.5 Observability

`seat_heartbeat` (every `desk_brief` call), `tool_calls_1m` rollups and gate outcomes feed `desk_roster_status`. Langfuse keeps LLM traces; the gateway does not duplicate them. A read-only status page is out of scope for v2.

---

## 8. Workstream D — Prompts, skills and memories (each seat owns its prompt; QUALITY owns shared directives and skills)

### 8.1 Prompt changes (`core-directives.xml` v1.1, every `bot-0N-*.xml` v1.1)

1. **Placeholders replace hardcoded ids.** `4d78b294-…` → `{{DESK_CHANNEL_ID}}`; every seat `<agent_uuid>` → `{{SEAT_UUID:LEAD}}` … `{{SEAT_UUID:QUALITY}}`; add `{{DESK_GATEWAY_URL}}` and `{{DESK_ROSTER_VERSION}}`. `scripts/assemble-prompts.sh` gains `--roster grokbot/rosters/<team>.json` and refuses to assemble with an unfilled placeholder. The Spectrum Web Co roster file is committed (ids are not secrets); a recipient team's roster is produced by `desk_doctor register` (§9.3).
2. **New `<tools>` section per seat**: points at `contracts/tool-rosters/<seat>.yaml`, lists the tool names, marks g5/g6 tools as PD-5 operations, and states the rule "a tool the gateway did not list does not exist; a tool call the gateway refused is a blocker, not a retry loop".
3. **New `<memory>` section**: which bank the seat writes (`pd-<seat>`), what to retain (decisions with receipt paths, environment facts, verified commands, review risks), what never to retain (secrets, unverified claims, other seats' work), and that `desk_brief` runs at turn start.
4. **New `<connectors>` section**: Marketplace connectors the seat may `@` (Linear, Notion, GitHub, Greptile, Slack for LEAD), with "prefer a connector over the browser".
5. **PD-8 in core directives**: external intake enters the desk only through LEAD (1:1 or `desk_intake_*`). A build seat that receives an outside request (another Bot, a Slack thread, a DM from a non-operator) records it and sends LEAD a held handoff; it does not act.
6. **Always-loaded skills** grow from one to three: `skills/verification-receipts`, `skills/desk-doctor`, `skills/desk-bootstrap`.
7. LEAD adds `desk_intake_next` to the Phase 0 poll ("Poll held handoffs, then poll intake") and gains a `<routines>` section: `desk-held-poll` (every 10 min) and `desk-intake-poll` (every 10 min, or on a GitHub `desk:intake` label event where the Cursor integration supports it).

### 8.2 New skills

| Skill | Owner | Purpose |
|---|---|---|
| `skills/desk-bootstrap/` | LEAD (last-match override) | First-run procedure for a Bot created from a template (§9.2). L1 fits in the template description |
| `skills/desk-doctor/` | QUALITY | `/desk doctor` → `desk_doctor check`; how to read the report; what a red line means; never "repair" a gate failure |
| `skills/desk-gateway/` | QUALITY | How to call gateway tools, gate tags, the 20 s deadline, fail-open vs fail-closed, what to do on 403 |
| `skills/hindsight-memory/` | QUALITY | Retain/recall discipline, bank rules, redaction, weekly reflect |
| `skills/ragflow-docs/` | QUALITY | When to search docs vs open the file; datasets; citing chunks |
| `skills/railway-tailscale/` | INFRA (under `skills/platforms/`) | Forwarders, ACL tags, cutover, rollback |
| `skills/tool-packs/` | QUALITY | Loading/unloading packs, the 20-tool ceiling, pack authoring rules |

Authoring rule from `skills/README.md` still applies: these are written because the class of mistake (wrong path, wrong host, secret in a message, unverified "done") has already occurred twice in this desk's history, not ahead of evidence.

### 8.3 Skill packaging for Grok Bot and other teams' work

Grok Bot skills live in one account-wide private library, so "enabled skills" in a template point at names in that library. Two packaging steps:

1. **Desk skill pack → Cursor team Marketplace plugin `swc-programming-desk`** (skills + the seven `desk.swcstudio.space` connector definitions). `grok-claude-cloud-connector/docs/grok-bot-setup.md` already anticipates "a Cursor team-marketplace plugin later". Until the plugin exists, `desk-bootstrap` pastes each SKILL.md with "Save this as a skill named …" (desktop only).
2. **Shared library → Grok Bot.** Add a `grok-bot` target to `agent-substrate/packages/projector` that emits the plugin manifest from `/root/agent-skills`, so skills mined by Hermes, Omp, Grok Build and the docs-scraper (for example `mcp-connector-context`, `objective-dev-loop`, `goal-decompose`, `docs-*`) reach the desk by the same PR-reviewed route. The desk pack itself is proposed back into `agent-skills` via `skills_propose`, so other desks (recruitment, trading) can adopt `desk-doctor` and the receipt discipline.

Marketplace plugins from other teams the desk should install account-wide and enable per seat: GitHub (all), Linear and Notion (LEAD, QUALITY), Slack (LEAD), Greptile (QUALITY), Vercel (WEB), Railway (INFRA) where a connector exists. Policy line for every prompt: prefer the connector, fall back to computer use, never both for one action.

---

## 9. Workstream E — Grok Bot share: install the desk from Add Bot

### 9.1 What a template can and cannot carry

A template (Share → Create template → **Team-only**) copies profile, settings, enabled skills, routines and avatar. It does not copy memory, conversation history, credentials, the computer, or group membership, and Grok Bot's own guidance says to strip secrets and internal URLs. So the seven templates carry:

| Field | Content |
|---|---|
| Name / label | `Programming Lead (LEAD)`, `Systems & Design (SYSTEMS)`, … `Quality & Security (QUALITY)` |
| Description (permanent rules) | The seat's `<role_charter>` statements, the line "First run: `/desk bootstrap`", the public gateway host, and nothing else |
| Enabled skills | `desk-bootstrap`, `desk-doctor`, `verification-receipts`, the seat's platform skill, plus the seat's `load="always"` list |
| Routines | LEAD: `desk-held-poll`, `desk-intake-poll` (paused until doctor is green). Seats: `desk-heartbeat` (daily `desk_brief`, paused until doctor is green) |
| Avatar | Seat avatar from `grokbot/avatars/` |
| Not in the template | UUIDs, channel id, XML prompt body, tokens, tailnet names, receipts |

### 9.2 Bootstrap sequence (`skills/desk-bootstrap`)

1. Recipient adds the seven templates (desktop; mobile can add but cannot run the connector card). Order does not matter.
2. Each new Bot is told `/desk bootstrap`. The skill has the Bot add the connector: **Add MCP Server** → name `desk-<seat>`, URL `https://desk.swcstudio.space/mcp/<seat>`, OAuth. The consent page asks for the team passphrase (held by Ove, rotated per team).
3. The Bot calls `desk_doctor register`: it reads its own agent UUID from `/home/box/agent-data/agents/<uuid>/` on the Bot computer (path from `ARCHITECTURE.md` §7; write access is an assumption to prove in n1), and the gateway records `seat → uuid` for that team.
4. Ove (or LEAD, once it exists) creates the group with LEAD + the five build seats and pastes the group id to LEAD; LEAD calls `desk_doctor register` with `channel_id`. QUALITY is never added to the group.
5. When `desk_roster_status` shows seven registrations and a channel id, every Bot runs `desk_doctor install_prompt`: the gateway renders `prompts-assembled/<SEAT>.xml` at the pinned tag with the roster filled in, and the Bot writes it to its `SYSTEM_PROMPT.xml`, then reports the SHA-256.
6. Every Bot runs `desk_doctor check`. LEAD un-pauses its routines only when all seven are green.
7. Memory seeding: `desk_brief` on first turn pulls `pd-desk` (shared facts) and the seat's own bank; a new team starts with an empty `pd-<seat>` and the shared bank's environment facts.

### 9.3 `desk_doctor check` — what "still integrated properly" means, as a report

| Check | Green when |
|---|---|
| Prompt | SHA-256 of the installed `SYSTEM_PROMPT.xml` equals the gateway's rendered `prompts-assembled/<SEAT>.xml` at `{{DESK_ROSTER_VERSION}}`; no unfilled `{{…}}` |
| Skills | Every `<skill path=…>` in the seat prompt resolves to a name present in the private skills library (the Bot lists `/` entries); versions match the tag |
| Memory | Hindsight `/health` reachable through the gateway; bank `pd-<seat>` exists; a retain/recall round trip with a redacted probe succeeds |
| Tools | `tools/list` count is within 10–15 (or ≤ 20 with a pack loaded) and equals `contracts/tool-rosters/<seat>.yaml`; every g5/g6 tool is marked |
| Connector | OAuth token valid for `seat:<name>`; a call to another seat's endpoint returns 403 |
| Roster | Channel id registered; LEAD in the group; QUALITY out; seven UUIDs registered; heartbeat within 24 h |
| Substrate | `desk_event_emit` lands in Greptime; `desk_docs_search` returns a hit for "verification receipt" |

Doctor reports; it never edits a gate, a receipt or another seat's files. `repair` re-runs `install_prompt` and connector re-auth only. The pattern is GrokRouter's `/router doctor`, which this team already ships.

### 9.4 Fresh-desk acceptance (the release gate for the share)

Modelled on `grokrouter/docs/FRESH-BOT-ACCEPTANCE.md`: a team member who has never had the desk adds the seven templates, runs bootstrap, and the following must pass with receipts: (1) seven doctors green; (2) Ove messages LEAD 1:1 with a docs-only ask; (3) LEAD runs the double uplift and dispatches one Lane C ticket; (4) the seat posts `awaiting-review / pending QUALITY` in the group; (5) QUALITY stamps `approved_by` via `desk_receipt_approve`; (6) `desk_roster_status` shows the events; (7) an outside `POST /v1/intake` reaches LEAD through `desk_intake_next` and is acknowledged back to the origin. Existing Bots are not a substitute for a fresh add.

---

## 10. Workstream F — Driving the desk from outside, speaking only to LEAD

| Entry | Mechanism | Who can use it |
|---|---|---|
| Human, desktop or mobile | LEAD ↔ Ove 1:1 (unchanged). Mobile can message, mention, approve and watch the computer; advanced configuration stays on desktop | Ove, team members with the LEAD template |
| Machines and other desks | `POST https://desk.swcstudio.space/v1/intake` with an **origin token** (`origin:github`, `origin:slack`, `origin:recruitment-desk`, `origin:cron`, `origin:shortcut`). Body: `origin`, `title`, `ask` (verbatim), `links[]`, `priority`, `requested_by`, `idempotency_key`. Inserted into Timescale `desk_intake` (which is the queue), evented to Greptime | Any holder of an origin token; seat tokens are rejected on this route |
| GitHub (stays the record) | Issue labelled `desk:intake` in a swcstudiospace repo → `.github/workflows/desk-intake.yml` (INFRA) posts to `/v1/intake` with the issue URL; LEAD's `desk_intake_ack` comments the Graph ID, Linear and Notion links back on the issue | Repo collaborators |
| Slack | Cursor's Slack integration triggers LEAD's `desk-intake-poll` routine on a message in `#programming-desk-intake` (where the integration supports it); otherwise the poll interval covers it | Team |
| Other Grok Bots | A Bot outside the group can DM LEAD; LEAD treats it as intake. Build seats treat any non-LEAD request as PD-8 and hold it | Other desks |

Only LEAD's endpoint exposes `desk_intake_next` and `desk_intake_ack`. The gateway refuses `/v1/intake` for seat tokens and refuses intake tools on non-LEAD endpoints, so the property "outside speaks only to LEAD" is enforced by the server, not by prompt text.

---

## 11. Repository changes in this repo

| Change | Owner | Notes |
|---|---|---|
| `docs/upgrade-plan-desk-v2.md` (this file) | QUALITY (`docs/**`) | Plan of record until superseded |
| `ownership.yaml` additions (Appendix A) | QUALITY | New paths owned before they exist so G-1 never sees an unowned file |
| `contracts/tool-rosters/<seat>.yaml`, `contracts/tool-packs/<app>.yaml` | QUALITY, `contract_surface: true`; consumers = the seats | Contract PR merges before gateway code (cross-bot protocol) |
| `services/desk-gateway/**` | SYSTEMS | FastAPI; tests with fixtures for every roster; no secrets |
| `infra/desk-gateway/**`, `infra/railway/**`, `infra/tailscale/**`, `.github/workflows/**` | INFRA | Units, nginx vhost, forwarder specs, intake workflow. Also copy `ci/.github/workflows/gates.yml` to `.github/workflows/gates.yml` so the gates finally run on PRs |
| `prompts/_shared/core-directives.xml` v1.1 (PD-8, placeholders, `<tools>`/`<memory>`/`<connectors>` templates) | QUALITY | Controlled document |
| `prompts/bot-0N-*.xml` v1.1 | Each seat | Seat-specific `<tools>`, `<memory>`, `<connectors>`, `<routines>` |
| `scripts/assemble-prompts.sh --roster` | QUALITY | Refuses unfilled placeholders |
| `grokbot/rosters/spectrumwebco.json`, `grokbot/templates/<seat>.md`, `grokbot/avatars/` | LEAD | Template descriptions are generated from the prompts, never hand-edited |
| New skills (§8.2) | As listed | |
| **G-7 desk integrity** — `ci/gates/check_desk_integrity.py` | QUALITY | Fails when: a roster has < 10 or > 15 tools; a roster tool lacks a schema; a g5/g6 tool lacks the approval/rollback fields; a prompt source contains a literal UUID or channel id; an assembled prompt contains `{{`; a template file contains a token shape or a tailnet name. Add to `run_all.py` and `ci/tests/test_gates.py` with fixtures |

---

## 12. Delivery — Graph of Thought for LEAD's kickoff

LEAD runs the first uplift from §1, then this graph (seven nodes, 5–6 steps each) through the kickoff checklist (Notion Agent Task Graph, Linear Spectrum Web Co, one issue per node, one sub-issue per step), then the second uplift with live URLs, then dispatch. The node contents are given here so the graph is task-specific rather than a template; LEAD may re-cut steps within 4–8.

**n1 · understand — Inventory and prove the assumptions** (LEAD; Lane C to INFRA for the Railway reads). Steps: (1) List both Railway projects' service names, ports and environments in Ove's account and record them (the mapping table in §5 is provisional). (2) Identify the `railway-app` tailnet node. (3) Prove a Bot can write its own `SYSTEM_PROMPT.xml` path and read its UUID; record the exact path. (4) Confirm whether Grok Bot's MCP client honours `tools/list_changed` (else packs use the fallback endpoints). (5) Confirm the Cursor team network policy (allowlist or open) and plan tier (Team Setup is Enterprise-only). (6) Record the results in `docs/upgrade-plan-desk-v2.md` §13 via a QUALITY docs ticket. Depends on: none.

**n2 · decompose — Network plane** (INFRA). Steps: (1) Deploy the Tailscale Forwarder into Ultrathink/production with the five mappings; tag `tag:railway-forwarder`; disable key expiry. (2) Deploy the forwarder into Agent Substrate/production with the Hindsight and RAGFlow mappings. (3) ACL: tags, grants, deny-by-default; verify from the VPS and from the Mac mini. (4) Cut `substrate.env` over to tailnet names; restart `substrate-mcp`; verify `/brief` and `events_emit`. (5) G-6: remove the TimescaleDB TCP proxy and Greptime public domain with recorded approval and a re-create rollback. (6) Receipt with `tailscale status`, port probes, `unverified` for anything not exercised. Depends on n1.

**n3 · generate — Substrate data planes** (SYSTEMS in `agent-substrate`). Steps: (1) Merge the companion docs PR (`data-planes.md`, `railway-tailscale.md`, env, roadmap). (2) Hindsight adapter behind `memory_write`/`memory_search` (banks `pd-*`), D-04 redaction, `/health` version gate; retire the Claude Code local `hindsight` stdio entry and set Hermes `memory.provider` to none (backup first). (3) Dragonfly adapter: brief, search and recall caches, rate counters, fail-through on outage (the 2026-09-26 "cache only" decision; the password now crosses the tailnet, which closes the Phase 8 plaintext-proxy concern). (4) Timescale migrations: `desk_intake`, `desk_claims`, `desk_idempotency`, `desk_receipts`, `seat_roster`, `tool_pack_state`, hypertables + continuous aggregates. (5) RAGFlow ingest job for `programming-desk` and `agent-substrate` datasets; `docs_search` wired. (6) Receipts per package with `bun test`. Depends on n2.

**n4 · generate — Desk Gateway and contracts** (QUALITY contract first, then SYSTEMS and INFRA in parallel). Steps: (1) Contract PR: seven `contracts/tool-rosters/*.yaml` and the first three `contracts/tool-packs/*.yaml`; consumers ack. (2) SYSTEMS: gateway skeleton, OAuth AS with per-seat clients, `/mcp/<seat>` routing, shared core eight tools, audit to Greptime. (3) SYSTEMS: seat tools in roster order, g5/g6 enforcement, 20 s deadline, fail-open/closed rules, fixture tests per roster. (4) SYSTEMS: intake API, origin tokens, `desk_intake_*`. (5) INFRA: `desk.swcstudio.space` DNS, nginx vhost, TLS, systemd unit, env template, allowlist entry if needed. (6) Smoke from a scratch Bot with the header key: `tools/list` on two seats differs; cross-seat call is 403. Depends on n3 for the data tools; the skeleton can start after n1.

**n5 · refine — Prompts, skills, templates, plugin** (QUALITY for shared, each seat for its prompt, LEAD for templates). Steps: (1) Placeholders and `--roster`; core directives v1.1 with PD-8 and section templates; G-7 gate + tests. (2) Each seat's prompt v1.1 (`<tools>`, `<memory>`, `<connectors>`, `<routines>`), assembled and parsed. (3) Skills in §8.2 written and reviewed. (4) `swc-programming-desk` Marketplace plugin (skills + connector definitions) and the `grok-bot` projector target in agent-substrate. (5) Seven Team-only templates created from the generated descriptions; screenshots of each Share card in the receipt. (6) Desk skill pack proposed into `agent-skills` via `skills_propose`. Depends on n4 (tool names must be final).

**n6 · critique — Fresh-desk acceptance and external intake** (LEAD orchestrates; QUALITY judges). Steps: (1) A fresh team member adds the seven templates and runs bootstrap; seven doctors green. (2) Docs-only ask through LEAD 1:1 → double uplift → Lane C ticket → `awaiting-review / pending QUALITY` → `desk_receipt_approve`. (3) `POST /v1/intake` from GitHub label and from `curl` with an origin token; LEAD acks back to the issue. (4) Mobile: Ove messages LEAD from iOS and approves a g5 tool call from the push notification. (5) Failure drills: gateway down (reads fail open, writes fail closed), forwarder down (`desk_db_health` red, no public fallback), Dragonfly down (same answers, uncached), wrong-seat token (403), pack ceiling (21st tool refused). (6) Open questions to Ove, if any, capped at four. Depends on n5.

**n7 · synthesize — Ordered rollout and rollback** (LEAD). Steps: (1) Order: n2 → n3 → n4 → n5 → n6 with n4 skeleton overlapping n3. (2) Rollback per node: forwarders can be deleted and proxies re-created; substrate env reverts by file; gateway is additive (Bots keep working without it, minus new tools); prompt v1.1 reverts by re-assembling v1.0 with the committed roster; templates are re-published. (3) Announce cutover windows in the Desk; LEAD dispatch notes as the audit trail. (4) Sync PR fields to Notion and Linear; report to Ove with receipt paths and every `unverified`. (5) Retire `railway-app` if superseded (G-6, after n6). Depends on n2–n6.

Runtime lanes: n2 and n5 are Lane C specialist tickets (clear ownership). n3 and n4 default to Lane A Cursor Cloud Agents with the second-uplift XML, Lane B only if Ove asks. Nothing here is a merge claim; `docs/github-sot-orchestration.md` §6 still lists Cloud Agent, Hermes and Greptile E2E as unverified.

---

## 13. Assumptions, ambiguities and what was not verified

| Item | Status | Resolves in |
|---|---|---|
| Railway service names (`greptimedb`, `timescaledb`, `dragonfly`, `hindsight-api`, `ragflow`) and ports (Greptime 4000/4001/4003, Timescale 5432, Dragonfly 6379, Hindsight 8888, RAGFlow 9380/80) | Assumed from defaults and the substrate env; the projects are not visible from this session's Railway connection | n1 |
| Bot can read its UUID and write `SYSTEM_PROMPT.xml` under `/home/box/agent-data/agents/<uuid>/` | Path stated in `ARCHITECTURE.md`; write access not proven | n1 |
| Grok Bot MCP client honours `tools/list_changed` | Unverified; fallback endpoints designed | n1 |
| Grok Bot allows a Bot to be created by another Bot | Unverified; the plan does not depend on it (D-3) | — |
| Cursor plan tier and network policy for the team | Unknown; Team Setup is Enterprise-only, hence D-2 | n1 |
| Which project `railway-app` (100.77.7.42) belongs to | Unknown | n1 |
| GitHub Actions on this repo | `.github/` is absent at the root; gates do not run in CI today | n5 step 1 |
| Play Developer API and App Store Connect API credentials for the gateway | Not inventoried; INFRA holds them as Team Secrets / gateway env | n4 step 3 |
| Hindsight version and embedding model on Railway | Template ships `v0.10.1-slim`; dimensions must be fixed before data is stored | n3 step 2 |
| `desk-intake-poll` event trigger via the Cursor GitHub/Slack integration | Availability per team unverified; the 10-minute poll is the floor | n6 step 3 |

Nothing was deployed, no tracker rows were created, no PR was merged, and no gate was weakened while writing this plan. The desk's E2E path (uplift → kickoff → Cloud Agent → Greptile → QUALITY → merge → sync) remains **not verified**, exactly as `docs/gotxcot-cloud-pipeline.md` records.

---

## Appendix A — `ownership.yaml` additions (applied in this PR)

```yaml
  # --- Desk v2: gateway, contracts, Grok Bot share (added 2026-09-30) ----------
  - pattern: "services/desk-gateway/**"
    owner: bot-01-systems-backend
  - pattern: "infra/desk-gateway/**"
    owner: bot-05-infrastructure
  - pattern: "infra/railway/**"
    owner: bot-05-infrastructure
  - pattern: "infra/tailscale/**"
    owner: bot-05-infrastructure
  - pattern: "contracts/tool-rosters/**"
    owner: bot-06-quality-security
    contract_surface: true
  - pattern: "contracts/tool-packs/**"
    owner: bot-06-quality-security
    contract_surface: true
  - pattern: "grokbot/**"
    owner: bot-00-programming-lead
  - pattern: "skills/desk-bootstrap/**"
    owner: bot-00-programming-lead
```

Also applied under `contract_consumers`: `"contracts/tool-rosters/**"` → all seven seats; `"contracts/tool-packs/**"` → `bot-02-web-edge`, `bot-03-android`, `bot-04-ios`. The block sits before the final `**/*.proto` rule so that rule stays last. `python3 ci/gates/check_ownership.py --validate-manifest` reports 98 rules OK on this branch. Broad `docs/**`, `skills/**`, `prompts/_shared/**` and `ci/gates/**` stay QUALITY; per-seat prompt files stay with their seats.

## Appendix B — Prompt additions (shape)

```xml
<tools contract="contracts/tool-rosters/ios.yaml" gateway="{{DESK_GATEWAY_URL}}/mcp/ios">
  <tool name="desk_brief" kind="read"/>
  <tool name="desk_testflight_status" kind="read"/>
  <tool name="desk_appstore_phased_release" kind="write" gates="g5 g6">PD-5: approval_id and rollback_plan required.</tool>
  <rule>A tool the gateway did not list does not exist. A refused call is a blocker for LEAD, not a retry loop.</rule>
</tools>
<memory bank="pd-ios" shared="pd-desk">
  <retain>Decisions with receipt paths; simulator and OS facts; review risks and their outcomes.</retain>
  <never>Secrets; unverified claims; another seat's work; transcripts.</never>
</memory>
<connectors>
  <connector name="github" prefer="true"/>
  <connector name="linear" via="LEAD"/>
</connectors>
```

## Appendix C — `contracts/tool-rosters/lead.yaml` (excerpt)

```yaml
seat: bot-00-programming-lead
endpoint: /mcp/lead
version: 1.0.0
consumers: [bot-00-programming-lead]
tools:
  - name: desk_intake_next
    kind: write
    gates: []
    input: { type: object, properties: { origin: { type: string } }, additionalProperties: false }
    backend: gateway.intake
  - name: desk_graph_state
    kind: write
    input:
      type: object
      required: [graph_id, node_id, action]
      properties:
        graph_id: { type: string, pattern: "^ut-" }
        node_id:  { type: string, pattern: "^n[1-8]$" }
        action:   { enum: [claim, release, complete] }
    backend: substrate.graph_claim|graph_release|graph_complete
```

## Appendix D — Companion changes in `swcstudiospace/agent-substrate`

`docs/data-planes.md` (policy table of §6 with schemas and bank names), `docs/railway-tailscale.md` (forwarders, ACL, cutover, rollback), `.env.example` (Hindsight and Dragonfly keys; tailnet hosts; Agentmemory removed), `README.md` and `.planning/PROJECT.md` data sections. See that PR.
