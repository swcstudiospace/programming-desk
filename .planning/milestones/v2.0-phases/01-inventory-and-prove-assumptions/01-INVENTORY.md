# Phase 1 — inventory evidence, not completion

Recorded 2026-10-08; Desk baseline `4f8e495e4eba1a799056adf3d4385522c59df359`. Status: **incomplete; acceptance unverified**. [Machine-readable evidence](01-INVENTORY.json) preserves the entire parent runtime input and all three bounded read-only source reports. [Seven-phase reconciliation](../../intel/implementation-map.md) groups authored capabilities/gaps. Parent live calls are **parent-observed**, not commands run by this worker. This is neither a deployment receipt nor an approval/doctor/publication claim.

## Railway scopes and listeners

Connected account display name: Ming Chen; workspace: Ming Chen's Projects. Names match the proposal, but account identity is not established as Ove's: ownership/authorization remains a prerequisite to mutation.

| Project | Project ID | Production environment ID |
|---|---|---|
| Ultrathink | `67a98752-ba0a-4ae2-a881-8d0e33a89328` | `6cfcb6de-3175-418b-8e20-7817a3d31633` |
| Agent Substrate | `a3453be1-819a-4ac3-a787-c6cfa5550f18` | `c50e0706-deb0-43ad-aaa0-53a92da3b396` |

| Project / service | Confirmed service ID | Observed listener / configuration distinction |
|---|---|---|
| Ultrathink / GreptimeDB | `b53b4c7d-df3c-4cd8-a15d-e5fb1a79e254` | SSH `/proc/net/tcp` state `0A`: `0FA0,0FA1,0FA2,0FA3` = 4000/4001/4002/4003, exit 0; describe-service also configured ports. Forwarder design maps only 4000/4001/4003 to `greptimedb.railway.internal`; 4002 is not authorized merely because it listens. Public HTTP domain present. |
| Ultrathink / TimescaleDB | `1bd7a6fd-b7b2-4fe4-8b4f-0d76ead81d79` | SSH `/proc/net/tcp` and `tcp6`: `1538` state `0A` = 5432, exit 0. Intended host `timescaledb.railway.internal`. Public TCP proxy remains `monorail.proxy.rlwy.net:49679`. |
| Ultrathink / Dragonfly | `32ee49a2-61bb-4572-acc8-1aa5956b6c7f` | SSH `/proc/net/tcp`: `00000000:18EB` state `0A` = 6379, exit 0. Intended host `dragonfly.railway.internal`. `ss` failed, not the listener proof. |
| Ultrathink / tailscale-vpn | `fcb79134-ca20-4816-8c10-ffaf18da5d7f` | Source `Andrew-Bekhiet/railway_tailscale_vpn`, deployment status SUCCESS; public domain target 1055 is configuration, not a recorded listener/application acceptance. SSH `printenv TAILSCALE_HOSTNAME` returned `railway-app`, exit 0. |
| Agent Substrate / hindsight-api | `0436123d-6fff-4bd8-a9a5-bd38db9ffff1` | SSH `/proc/net/tcp`: `22B8` state `0A` = 8888, exit 0; domain target agrees. Image configured `ghcr.io/vectorize-io/hindsight-api:0.9.1`; public domain present. Intended mapping `8888:hindsight-api.railway.internal:8888`. |
| Agent Substrate / ragflow | `8ddda0d9-44d4-4e7a-8eec-6dbf91bb8d9e` | SSH `/proc/net/tcp`: `24A4,24A6,0050` state `0A` = 9380/9382/80, exit 0; describe-service agrees. Public domains present. Design maps API 9380 and optional web 80 to `ragflow.railway.internal`; 9382 is observed, not automatically authorized. |

Service inventory, including ancillary names (IDs not supplied for ancillary services):

- **Ultrathink:** Routines, OpenBot, Postgres, Agent, Gate, Dragonfly, tailscale-vpn, TimescaleDB, GreptimeDB.
- **Agent Substrate:** hindsight-llm-bridge, hindsight-worker, hindsight-control-plane, Postgres, hindsight-api, ragflow-oauth-integration, ragflow-oauth-service, ragflow, elasticsearch, storage, mysql, redis.

Agent Substrate inventory has no forwarder service. Neither planned named forwarder is present in observed tailnet status. Service listeners show processes listening **inside those containers**; they do not prove private DNS resolution, TCP traversal, authenticated APIs, per-client authorization or cutover.

## Parent-observed local, tailnet and public state

- `tailscale status --json`, exit 0: self `vps`; `railway-app` `100.77.7.42` online, matched by Railway hostname proof to Ultrathink/production/tailscale-vpn. Advertised routes: `10.128.0.0/9`, `fd12:4f8:a4d6:1::/64`, `fd12::10/128`. It is an observed subnet-route advertiser, **not a verified per-project forwarder** or a retirement approval. Mac mini online; XPS application-port reachability not recorded. `grok-bot-box` `100.94.38.2` offline, last seen `2026-10-02T02:45:28.1Z`.
- Gateway systemd state active; `http://127.0.0.1:8791/health` returned health `ok`, version `0.1.0`, seven seat endpoints, packs clippyos/desklanes/kanbanos; registered seats `[]`, channel registered `false`. Loopback health does not establish public OAuth, Bot access or installed desk.
- `https://desk.swcstudio.space/health` public reader failed DNS `ETIMEOUT`; bounded DNS command `getent ahostsv4 desk.swcstudio.space` exited 2, empty output. No public gateway health success was observed.
- Substrate systemd active. Command `curl --silent --show-error --max-time 15 --write-out '\nHTTP %{http_code}\n' http://127.0.0.1:7410/healthz` exited 0 but HTTP **503**. Body: `{"index":false,"greptime":false,"appendOnly":null,"eventsWritable":false,"briefP95":1,"eventP95":3}`. Transport success is not healthy data planes or successful brief/events persistence.
- Public Hindsight `https://hindsight-api-production-014d.up.railway.app/health`: `{"status":"healthy","database":"connected","db_acquire_ms":9.3,"db_pool_waiting":0,"db_pool_in_use":0,"db_pool_max":100,"db_pool_idle":1}`. This proves that endpoint's health response only, not tailnet access, server-reported version, embeddings/dimensions, `pd-*` banks, redaction, retained evidence or Desk cutover. Image 0.9.1 differs from proposal §13's template v0.10.1-slim assumption; neither is a live compatibility check.
- Authenticated Cursor access attempt `browser.open` relay target `cursor.com` timed out after 12000 ms; zero browser tabs remained. Team tier/network policy was not obtained.
- Filtered Railway logs: tailscale filters `railway-app`/`hostname`, Dragonfly filters `6379`/`listening`, no entries. Those failed to establish identity/listeners; the later SSH/kernel evidence does. Dragonfly `ss` attempt: `ss: command not found`, exit 127; kernel listener fallback established 6379.
- Current mounted xd registry had no Grok Bot UUID-read/prompt-write tools. Offline `grok-bot-box` and tool absence **do not establish the separate Grok Bot SaaS client's capabilities** or inability to read UUID/write prompt. Obtain evidence through the actual authenticated client/account UI.

The parent added the actual six mapped-service SSH invocations and observed result excerpts to `parent_command_supplement` in the JSON. Individual probe timestamps were not captured. The original raw input also omitted log time windows, deployment SHA, public-reader status codes and the systemd command string; these omissions remain disclosed rather than reconstructed as executed evidence.

## Concrete outstanding n1 requirements

Acceptance source: [proposal §12 n1 / §13](../../../docs/upgrade-plan-desk-v2.md); governance: [operating model](../../../docs/desk-operating-model.md), [ownership](../../../ownership.yaml), [resolved choices](../../INGEST-CONFLICTS.md).

1. **Inventory scope:** preserve discovered project/environment/service/listener IDs above; confirm actual account ownership and authorized scope. Listener proof is partial n1 evidence, not deployed network acceptance. Ancillary IDs were not recorded and no other environment inventory was supplied.
2. **Identify railway-app:** production service/node identity and advertised routes are observed. Determine actual router/forwarder role/configuration and disposition with replacement/acceptance dependencies; retirement requires genuine G-6 approval after n6.
3. **Actual Bot path/capabilities:** prove an authenticated Bot reads its own UUID and writes/reads back its own `SYSTEM_PROMPT.xml`; record exact actual path and bounded safe evidence. `/home/box/agent-data/agents/<uuid>/SYSTEM_PROMPT.xml` is currently a documented target only. No successful Bot probe occurred.
4. **Client notification:** exercise actual SaaS MCP `tools/list_changed` behavior. If unsupported, prove designed pack fallback endpoints rather than inferring support/absence from local host connectivity.
5. **Cursor policy/tier:** authenticated authorized account evidence of allowlist/open egress and team plan; Team Setup requires Enterprise. Ensure public gateway allowlist entry where required. Relay timeout is an attempted probe, not policy evidence.
6. **Record proposal §13 through QUALITY:** `.planning/**` is LEAD-owned; proposal doc is QUALITY-owned. Route the exact findings/corrections as an actual QUALITY docs ticket. No unowned source edit or fabricated ticket was made here. Correct root workflow absence and Railway visibility/identity; retain all still-unverified assumptions and version discrepancy.

Downstream real gates remain: tagged persistent exact-port forwarders and VPS/Mac mini/XPS probes; authenticated data-plane/version/bank/embedding/migration/ingestion acceptance; genuine mutation/independent exact-SHA approval; seven human-installed/published Team-only templates/plugin/skills; fresh-recipient, iOS and intake evidence; ordered rollout/rollback. Weekly reflect is resolved policy, not an exercised schedule. Authorized UI activation is required while `skills.approve` is absent.

Not exercised by parent record: Bot UUID read/prompt write; Grok MCP notification support; Cursor policy/tier; forwarder deployment; network cutover; database mutation; Team-only publication; fresh-desk acceptance; iOS approval; independent review approval. The original evidence worker performed no tests/build/lint/formatters/validation gates/smoke/install/deploy/commit/push. Parent-owned initialization smoke is recorded below; no consolidated suite, phase acceptance, or independent gate approval is recorded.

## Companion checkout provenance (observed after maps, not the map snapshot)

Parent-observed `swcstudiospace/agent-substrate` checkout after the bounded source maps: HEAD `21652a20a1b3ca98132e80ca76aadedc95c3369d` on branch `claude/greptime-events-ledger-7j1so8`, 15 commits behind its upstream. Preserved user work: modified `.planning/ROADMAP.md` and `packages/mcp-server/src/store-lock.test.ts`; deleted older `.planning/phases/0.5-governance/CONTEXT.md` and `.planning/phases/00-brief/0-UAT.md`; untracked archived governance/brief directories and `.planning/phases/v1.1-memory-bank-realtime/`. This current dirty-HEAD observation is not the exact source state during the earlier agent reads; current-source applicability must be re-established before Phase 3 companion implementation. No fetch/reset/switch/restore/commit was performed.

## Phase 1 follow-up discovery

- Actual GitHub metadata, acquired read-only by `InspectDeskRemoteCI` at `2026-10-08T03:12:24Z`: Quality Gates workflow `370453712` is **active**, Actions is enabled, and [PR 65](https://github.com/swcstudiospace/programming-desk/pull/65) is open on the unchanged baseline SHA. The [applicable run](https://github.com/swcstudiospace/programming-desk/actions/runs/37697523618) completed **failure**; gate-self-test succeeded, G-2 failed, and G-3…G-7 were skipped. The parent subsequently read the actual failed job log: `'approved_by' is missing — work must be reviewed by someone else`. No approval was manufactured and no workflow was rerun. Historical runner execution does not prove future runner eligibility or billing status.
- Two further actual Cursor browser attempts, default managed and explicit Chromium modes, failed because the browser-relay extension never connected. Cleanup returned zero tabs. Neither account tier nor egress policy was obtained; these failures are not SaaS capability verdicts.
- Notion reports `create_pages` and `update_page` **available**, and `query_data_sources` **available_with_limit**. The actual Agent Task Graph collection schema and enhanced Markdown specification were fetched. These are reachable tools, not successful materialization or proven collection write permissions; no actual access/quota denial was reported.
- Parent ran `python3 /tmp/desk-v2-bootstrap-smoke.py`, exit 0: 217 stable requirements, 217 unique primary-phase rows, 33 source constraints, seven source nodes, 41 source steps, three parsed JSON artifacts and 94 resolving local links. Completed requirements remain zero. This proves initialization integrity only, not phase acceptance or implemented behavior.

Exact attributed commands, timestamps, returned metadata and browser failures are retained in `phase1_followup_evidence` in [the inventory JSON](01-INVENTORY.json). Runtime observations remain bounded; every outstanding human and downstream acceptance gate above remains in force.
