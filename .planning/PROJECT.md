# Programming Desk v2

## What This Is

Programming Desk v2 is Ove's seven-seat programming desk, installed from seven Team-only Grok Bot templates and bootstrapped into a six-member group with QUALITY independent and off-channel. Its VPS Desk Gateway exposes contract-defined tools per seat, connects to five Railway data services through private project forwarders, and admits outside work only through LEAD.

The current milestone is **v2.4 — Multi-Region Edge Federation & Autonomous Chaos Recovery**: multi-region edge ingress routing, distributed DragonflyDB rate limiting, cross-region WAN inter-seat routing, high-latency vector clock convergence, and autonomous chaos recovery.

## Core Value

A fresh team can install a seven-seat desk whose work, tools, memory and approvals are independently evidenced and safely governed.

## Requirements

### Validated

- ✓ Phase 1: Inventory and prove assumptions — REQ-INVENTORY-001 through REQ-INVENTORY-016 (v2.0)
- ✓ Phase 2: Network plane — REQ-NETWORK-001 through REQ-NETWORK-022 (v2.0)
- ✓ Phase 3: Substrate data planes — REQ-DATA-001 through REQ-DATA-038 (v2.0)
- ✓ Phase 4: Desk Gateway and contracts — REQ-GATEWAY-001 through REQ-GATEWAY-054 (v2.0)
- ✓ Phase 5: Prompts, skills, templates, plugin — REQ-SHARE-001 through REQ-SHARE-040 (v2.0)
- ✓ Phase 6: Fresh-desk acceptance and external intake — REQ-ACCEPT-001 through REQ-ACCEPT-034 (v2.0)
- ✓ Phase 7: Ordered rollout and rollback — REQ-ROLLOUT-001 through REQ-ROLLOUT-013 (v2.0)
- ✓ Phase 8: Gateway Resiliency & Subagent Execution Drills — REQ-DRILL-001 through REQ-DRILL-010 (v2.1)
- ✓ Phase 9: External Intake Hardening & Telemetry Anchoring — REQ-INTAKE-001 through REQ-INTAKE-010 (v2.1)
- ✓ Phase 10: Multi-Desk Federation & Inter-Seat Routing — REQ-FED-001 through REQ-FED-005 (v2.2)
- ✓ Phase 11: Automated Staging & VPS Environment Promotion — REQ-STAGE-001 through REQ-STAGE-005 (v2.2)
- ✓ Phase 12: Production Cutover & Dynamic Failover — REQ-CUTOVER-001 through REQ-CUTOVER-005 (v2.3)
- ✓ Phase 13: Advanced Telemetry, SLOs & Alert Thresholds — REQ-ALERT-001 through REQ-ALERT-005 (v2.3)

All 257 requirements shipped and verified across Milestones v2.0, v2.1, v2.2, and v2.3.

### Active (Milestone v2.4)

- Phase 14: Multi-Region Edge Federation & WAN Routing — REQ-EDGE-001 through REQ-EDGE-005
- Phase 15: Autonomous Chaos Recovery & Self-Healing Resilience — REQ-CHAOS-001 through REQ-CHAOS-005

### Out of Scope

- Read-only status page — explicit source §7.5 exclusion.
- Bot tailnet enrollment or database credentials — locked D-2 requires public HTTPS gateway and substrate credential custody.
- Durable Dragonfly queues, sessions, locks or pub/sub — cache-only policy; Timescale is coordination authority.
- Reliance on Bot-created Bots — locked D-3 uses actual seven-template recipient setup.
- Unrelated `web/desk3d/**` — user-owned work outside the milestone bootstrap.

## Context

Approved source: [docs/upgrade-plan-desk-v2.md](../docs/upgrade-plan-desk-v2.md), including §§5–13 and Appendices A–D. Current technical/governance constraints: [docs/desk-operating-model.md](../docs/desk-operating-model.md). The original proposal's absence/no-deploy statements describe its authoring session, not the current repository. [Normalized synthesis](intel/SYNTHESIS.md), [requirements evidence](intel/requirements.md), [constraints](intel/constraints.md), [decisions](intel/decisions.md), [context](intel/context.md) and [classification](intel/classifications/desk-v2.json) preserve source detail and discrepancies.

The actual user selected **Initialize from Desk v2 plan**, resolved the three source warnings, then explicitly selected **Create planning setup**. [INGEST-CONFLICTS.md](INGEST-CONFLICTS.md) records zero documentary blockers, zero open warnings and 12 INFO entries. This routing approval is not production mutation, destructive-operation approval, skill activation, reviewer approval or runtime acceptance.

Evidence-worker-owned durable artifacts: [implementation map](intel/implementation-map.md), [Phase 1 inventory](phases/01-inventory-and-prove-assumptions/01-INVENTORY.md), [machine inventory](phases/01-inventory-and-prove-assumptions/01-INVENTORY.json). Fixed paths are referenced without reading incomplete output. Parent-supplied observations include actual five-service listener and railway-app project identity proof; local gateway health but no seats/channel registration; failed public DNS; substrate healthz HTTP 503; offline grok-bot-box; absent planned forwarders; public Hindsight health without version/bank/embedding/cutover proof. Browser relay timeout and absent mounted UUID/prompt-write tools do not prove the separate Grok Bot SaaS client is unavailable.

## Constraints

- **Security**: Bot/template carries no database/upstream credentials, tokens, internal tailnet names or receipt bodies. D-04 redaction precedes ledger/memory/ingest; RAGFlow excludes receipts/transcripts. Secrets stay privately in authorized runtime env.
- **Topology**: Ultrathink has GreptimeDB/TimescaleDB/DragonflyDB; Agent Substrate has Hindsight/RAGFlow. One private-network forwarder per project/environment, persistent identity. Approved ports are 4000/4001/4003/5432/6379 and 8888/9380, with 80 optional. Observed 4002/9382 listeners never expand ACL mappings.
- **Data**: Greptime append-only chain/hourly Solana devnet anchor/180 hot days then export; Timescale transactional queue/claims/30-day idempotency and source retention; Dragonfly cache TTLs/fail-through; Hindsight verified forever-retained facts and weekly reflection; RAGFlow redacted heading-aware docs/last-five dataset versions. GitHub remains shipped-work truth.
- **Gateway**: Python/FastAPI, bind 127.0.0.1:8791, public desk.swcstudio.space through TLS/nginx/systemd. Seat OAuth/scopes/24-hour access/30-day refresh, cross-seat 403; every core/seat/initial-pack tool and backend retained; base 10–15, pack ≤5, live ≤20; 20-second deadline, read-open/write-closed, no public DB fallback.
- **Governance**: G-1–G-6 intact, G-7 additive. QUALITY contracts and real consumer acknowledgements precede implementation. True independent exact-current-SHA approval without a new tip and current Greptile COMPLETED govern merge claims; source fixtures/old receipts do not satisfy runtime gates.
- **Human authority**: Authorized account owner reviews and installs/enables skills/plugin through account UI; seats remain proposal-only while skills.approve is absent. Actual activation/Team-only publication, fresh recipient, mobile approval, team passphrase, account authorization and G-5/G-6 evidence remain checkpoints. Human loop acknowledgements are ticket/turn-scoped, not destructive approvals.
- **Cross-repo**: agent-substrate owners deliver companion docs/env/README/PROJECT Data, GSD replan of Phases 5/7/8, real adapters/migrations/ingest/ledger and grok-bot projector. agent-skills maintains actual proposal/review. Runtime owners back up before Claude/Hermes memory migration. No external repo edit occurs in bootstrap.
- **Ownership**: .planning and grokbot/bootstrap LEAD; source plan §13, shared prompts/assembly/gates/contracts/broad docs QUALITY; gateway SYSTEMS; infra/workflows/network skill INFRA; each seat owns its prompt. Last-match-wins and contract consumers apply before path edits.
- **Execution**: Current branch `bot-00-programming-lead/desk-swarm-subagents` remains unchanged. n2/n5 use Lane C; n3/n4 default Lane A, Lane B only on Ove request. Only gateway skeleton overlap after n1 is allowed; final Phase 4 depends on Phase 3. Parent owns checks, commits and push; this bootstrap creates no PLAN/SUMMARY and runs no gates/tests/build/install/deploy.

## Key Decisions

| Decision | Rationale | Outcome |
| --- | --- | --- |
| D-1: fixed five-service placement | Explicit source §3 lock; Hindsight replaces Agentmemory | Locked; runtime acceptance pending |
| D-2: VPS gateway plus private Railway forwarders | Bots neither join tailnet nor hold DB credentials; verified cutover precedes exposure retirement | Locked; runtime acceptance pending |
| D-3: seven Team-only templates with bootstrap/doctor | Fresh recipient can install; QUALITY stays out of six-seat group | Locked; publication/acceptance pending |
| D-4: no merge/tracker/deploy from original authoring session | Explicit original-session scope, not indefinite execution ban | Locked scope preserved |
| RW-01: Weekly reflect | Actual user resolution of original nightly/weekly discrepancy | Selected; no nightly/split-bank schedule; execution pending |
| RW-02: Mac mini and XPS alongside VPS | Actual user resolution; exact mapped ports and deny-by-default | Selected; ACL/probes pending |
| RW-03: Authorized human operator | Actual user chooses account-UI review/install/enable; no skills.approve invented | Selected; actual activation/publication pending |
| Exact-SHA/no-new-tip approval_ref | Independent QUALITY approval must not generate an unreviewed tip | Required; mechanism/runtime approval pending |
| Create planning setup | Separate explicit user routing choice after all three resolutions | Core planning authorized, not runtime clearance |
| Full fixed seven-phase scope | Preserve every source step/invariant and 217 stable IDs | All 7 phases executed, verified, and shipped |

## Evolution

After each verified transition, update active/validated requirements and decisions only from actual evidence, preserving unverified limits. At milestone closure review scope, source crosswalk, external receipts and human checkpoints; do not infer completion from initialized files.

---
*Last updated: 2026-10-08 after v2.2 milestone initialization.*
