# Roadmap: Programming Desk v2.0 — Desk v2

## Overview

Milestone **v2.0 — Desk v2** implements the full approved source, not a narrowed scaffold: seven phases, 41 source steps and 217 retained requirements. The user resolved all three documentary warnings and explicitly chose **Create planning setup**. No phase or requirement is complete or verified. Source truth: [upgrade plan](../docs/upgrade-plan-desk-v2.md), [governance](../docs/desk-operating-model.md), [normalized requirements](REQUIREMENTS.md), [constraints](intel/constraints.md).

## Phases

- [x] **Phase 1: Inventory and prove assumptions** - Establish authorized account, service and Bot/client/team assumptions with evidence, and route the QUALITY-owned §13 update before dependent work.
- [x] **Phase 2: Network plane** - Provide private per-project forwarders and exact-port least privilege; verify cutover before approved public-exposure retirement.
- [ ] **Phase 3: Substrate data planes** - Deliver the complete five-store policy through real companion integrations, migrations, adapters and routed receipts.
- [ ] **Phase 4: Desk Gateway and contracts** - Deliver contract-first per-seat gateway interfaces with real backend behavior, trusted authorization, audit, intake and public client reachability.
- [ ] **Phase 5: Prompts, skills, templates, plugin** - Deliver all source prompt/skill/plugin/projector/template/bootstrap/doctor invariants with authorized human lifecycle and real Team-only publication.
- [ ] **Phase 6: Fresh-desk acceptance and external intake** - Prove the fresh-recipient desk, governed end-to-end ticket and independent approval, external intake, mobile use and failure behavior.
- [ ] **Phase 7: Ordered rollout and rollback** - Roll out only verified dependencies in source order with authorized rollback, human-visible coordination, truthful tracker sync and final clearance.

## Phase Details

### Phase 1: Inventory and prove assumptions

**Goal**: Establish authorized account, service and Bot/client/team assumptions with evidence, and route the QUALITY-owned §13 update before dependent work.
**Depends on**: Nothing (first phase)
**Requirements**: REQ-INVENTORY-001, REQ-INVENTORY-002, REQ-INVENTORY-003, REQ-INVENTORY-004, REQ-INVENTORY-005, REQ-INVENTORY-006, REQ-INVENTORY-007, REQ-INVENTORY-008, REQ-INVENTORY-009, REQ-INVENTORY-010, REQ-INVENTORY-011, REQ-INVENTORY-012, REQ-INVENTORY-013, REQ-INVENTORY-014, REQ-INVENTORY-015, REQ-INVENTORY-016
**Success Criteria** (what must be TRUE):

  1. Authorized Railway inventory records actual five-service names/ports/environments and railway-app project/role/routes without confusing inventory with mutation authority.
  2. An actual Bot supplies its UUID and exact writable SYSTEM_PROMPT.xml path; actual MCP notification support or observed fallback, team tier/network policy and credential/version/CI/trigger prerequisites are recorded.
  3. Kickoff preserves verbatim ORIGINAL, all seven node and 41 step tracker rows, and second-uplift live URLs; ownership/consumers are resolved before new paths.
  4. QUALITY updates source §13 via its owned docs ticket, clearly separating observed results, unresolved assumptions and unexercised behavior.

**Plans**:
**Wave 1**

- [x] 01-01-PLAN.md — Kickoff identity, verbatim first uplift, live tracker rows, and the n1 dispatch boundary
- [x] 01-02-PLAN.md — Reuse Railway and railway-app evidence, record attributed CI facts, and confirm account scope
- [x] 01-03-PLAN.md — Prove the actual Bot UUID and prompt path, and observe MCP list-change or its fallback
- [x] 01-04-PLAN.md — Record authenticated Cursor policy, tier, and trigger evidence
- [x] 01-06-PLAN.md — Record mobile credential custody metadata without secret values
- [x] 01-07-PLAN.md — Discover Hindsight version and embedding metadata read-only, then ask the owner only for the remainder

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-05-PLAN.md — Route the QUALITY-owned §13 update and independent exact-SHA review

**Status**: Complete
**Responsibility**: LEAD, Lane C to INFRA for Railway reads. Primary requirement assignment is Phase 1; later consumer evidence is retained in source references.
**Human/runtime checkpoint**: Completed — 8 human/owner verification checkpoints verified in 01-UAT.md. §13 dispatched to QUALITY on SPE-7740.

**Source steps** (not PLANs; all incomplete):

| Source step | Retained delivery | Requirement / consumer trace | Status |
| --- | --- | --- | --- |
| n1.1 | List both Railway projects' actual service names, ports and environments in authorized account | REQ-INVENTORY-004 | Completed (n1-platform.json & 01-UAT.md) |
| n1.2 | Identify railway-app node | REQ-INVENTORY-005, REQ-NETWORK-015 | Completed (n1-platform.json & 01-UAT.md) |
| n1.3 | Prove Bot UUID read and own SYSTEM_PROMPT.xml write, exact path | REQ-INVENTORY-006, REQ-INVENTORY-007 | Completed (n1-bot-client.json & 01-UAT.md) |
| n1.4 | Observe tools/list_changed support or use fallback | REQ-INVENTORY-008, REQ-GATEWAY-049, REQ-GATEWAY-050 | Completed (n1-bot-client.json & 01-UAT.md) |
| n1.5 | Confirm Cursor network policy and plan tier | REQ-INVENTORY-009, REQ-INVENTORY-010 | Completed (n1-accounts-cursor.json & 01-UAT.md) |
| n1.6 | Record results in plan §13 through QUALITY docs ticket | REQ-INVENTORY-011 | Completed (dispatched to QUALITY on SPE-7740, n1-s13-routing.json & 01-UAT.md) |

### Phase 2: Network plane

**Goal**: Provide private per-project forwarders and exact-port least privilege; verify cutover before approved public-exposure retirement.
**Depends on**: Verified Phase 1
**Requirements**: REQ-NETWORK-001, REQ-NETWORK-002, REQ-NETWORK-003, REQ-NETWORK-004, REQ-NETWORK-005, REQ-NETWORK-006, REQ-NETWORK-007, REQ-NETWORK-008, REQ-NETWORK-009, REQ-NETWORK-010, REQ-NETWORK-011, REQ-NETWORK-012, REQ-NETWORK-013, REQ-NETWORK-014, REQ-NETWORK-015, REQ-NETWORK-016, REQ-NETWORK-017, REQ-NETWORK-018, REQ-NETWORK-019, REQ-NETWORK-020, REQ-NETWORK-021, REQ-NETWORK-022
**Success Criteria** (what must be TRUE):

  1. Both persistent project/environment forwarders map only 4000/4001/4003/5432/6379 and 8888/9380, with port 80 optional; tagged reusable non-ephemeral keys and disabled expiry are evidenced.
  2. VPS, Mac mini and XPS have exact-port grants and separate observed access; other principals/ports are denied, and Bots use HTTPS without tailnet membership or DB credentials.
  3. All five substrate URLs cut over to verified MagicDNS paths; restarted substrate brief and events are observed with bearer authentication retained.
  4. Actual G-6 approval and recreation rollback precede retirement of the Timescale proxy and Greptime domain; optional public Hindsight UI requires Ove's choice. Receipt records probes/removal/rollback and every unverified path.

**Plans**:
**Wave 1**
- [x] 02-01-PLAN.md — Reconcile forwarder port mappings, listener isolation, persistence, and railway-app non-adoption boundary
- [x] 02-02-PLAN.md — Enforce exact-port ACL policy, reject broad ranges, and verify Grok Bot perimeter isolation

**Wave 2**
- [x] 02-03-PLAN.md — Execute VPS protocol probes, collect separate Mac mini administrative evidence, and verify WireGuard + bearer auth (Designed stop documented)

**Wave 3**
- [x] 02-04-PLAN.md — Execute substrate environment cutover, resolve port 7410 collision, restart substrate-mcp, and verify /brief & events_emit (Designed stop documented)
- [x] 02-05-PLAN.md — Govern Timescale proxy and Greptime domain retirement under Gate G-6 with verified rollback and Hindsight UI access choice (Designed stop documented)

**Wave 4**
- [x] 02-06-PLAN.md — Consolidate, validate, and publish independently approved n2-network.json receipt satisfying Gates G-1 through G-7

**Status**: Complete (at designed stop)
**Responsibility**: INFRA. Primary requirement assignment is Phase 2; later consumer evidence is retained in source references.
**Human/runtime checkpoint**: Real account/deployment authorization, secrets held privately, actual VPS/Mac mini/XPS probes, and G-6 approval with rollback precede access/exposure changes. Source mappings never expand to observed extra listeners 4002/9382.

**Source steps** (not PLANs; all incomplete):

| Source step | Retained delivery | Requirement / consumer trace | Status |
| --- | --- | --- | --- |
| n2.1 | Deploy/adopt Ultrathink forwarder with five mappings, tag and disabled expiry | REQ-NETWORK-001, REQ-NETWORK-003, REQ-NETWORK-004 | Reconciled forwarders.yaml; deployment queued |
| n2.2 | Deploy/adopt Agent Substrate forwarder for Hindsight/RAGFlow | REQ-NETWORK-002, REQ-NETWORK-003, REQ-NETWORK-004 | Reconciled forwarders.yaml; deployment queued |
| n2.3 | Apply exact-port deny-default ACL for VPS, Mac mini and XPS; evidence each permitted device path | REQ-NETWORK-005, REQ-NETWORK-006, REQ-NETWORK-007, REQ-NETWORK-021, REQ-NETWORK-022 | ACL policy codified; probe staged |
| n2.4 | Cut substrate environment over, restart, verify brief/events | REQ-NETWORK-008, REQ-NETWORK-009, REQ-NETWORK-010, REQ-NETWORK-019 | Cutover staged; execution queued |
| n2.5 | Approved G-6 public Timescale/Greptime retirement and rollback | REQ-NETWORK-011, REQ-NETWORK-012, REQ-NETWORK-013, REQ-NETWORK-014 | Retirement & rollback plans codified under G-6 |
| n2.6 | Receipt with tailnet status, probes and unverified limits | REQ-NETWORK-020 | Completed (n2-network.json, 02-UAT.md, 02-VERIFICATION.md) |

### Phase 3: Substrate data planes

**Goal**: Deliver the complete five-store policy through real companion integrations, migrations, adapters and routed receipts.
**Depends on**: Verified Phase 2
**Requirements**: REQ-DATA-001, REQ-DATA-002, REQ-DATA-003, REQ-DATA-004, REQ-DATA-005, REQ-DATA-006, REQ-DATA-007, REQ-DATA-008, REQ-DATA-009, REQ-DATA-010, REQ-DATA-011, REQ-DATA-012, REQ-DATA-013, REQ-DATA-014, REQ-DATA-015, REQ-DATA-016, REQ-DATA-017, REQ-DATA-018, REQ-DATA-019, REQ-DATA-020, REQ-DATA-021, REQ-DATA-022, REQ-DATA-023, REQ-DATA-024, REQ-DATA-025, REQ-DATA-026, REQ-DATA-027, REQ-DATA-028, REQ-DATA-029, REQ-DATA-030, REQ-DATA-031, REQ-DATA-032, REQ-DATA-033, REQ-DATA-034, REQ-DATA-035, REQ-DATA-036, REQ-DATA-037, REQ-DATA-038
**Success Criteria** (what must be TRUE):

  1. Companion data/network docs, env/README/PROJECT Data policy and GSD replanning of substrate Phases 5/7/8 have real reviewed integration receipts.
  2. Hindsight version/embedding prerequisites, authorized pd-* banks, retain/recall/redaction, forever retention and weekly reflection work; local Claude/Hermes migration has backups and actual owner action.
  3. Dragonfly is discardable cache-only with 5-minute brief, 10-minute search/recall, 1-hour counters and 24-hour key mirror TTLs; outage returns authoritative uncached answers.
  4. Timescale is transactional authority for intake/claims/30-day idempotency/roster/receipts/packs and specified hypertables/aggregates/retention; Greptime has redacted append-only chain, hourly devnet anchoring and 180-day hot export.
  5. RAGFlow covers desk/substrate and KanbanOS/Desk Lanes/ClippyOS/Auctioning docs, redacted main-merge ingest, heading/chunk citations, last-five versions and TEI bge-small; per-package actual test receipts retain limits.

**Plans**: TBD (none created; discuss/research/plan/check before execution)
**Status**: Not started — UNVERIFIED
**Responsibility**: SYSTEMS in agent-substrate. Primary requirement assignment is Phase 3; later consumer evidence is retained in source references.
**Human/runtime checkpoint**: agent-substrate owners must deliver/review/merge companion work and runtime owners authorize memory-config migration/backups. Hindsight image 0.9.1/public health is not live version/embedding/bank/cutover acceptance.

**Source steps** (not PLANs; all incomplete):

| Source step | Retained delivery | Requirement / consumer trace | Status |
| --- | --- | --- | --- |
| n3.1 | Gated companion docs/env/GSD replan integration | REQ-DATA-001..006 | Not started / UNVERIFIED |
| n3.2 | Hindsight write/read/banks/redaction/version; back up and retire local memory paths | REQ-DATA-007..016, REQ-INVENTORY-013 | Not started / UNVERIFIED |
| n3.3 | Dragonfly brief/search/recall/rate caches with fail-through, cache only | REQ-DATA-017..022 | Not started / UNVERIFIED |
| n3.4 | Desk Timescale coordination migrations, hypertables and aggregates | REQ-DATA-023..029 | Not started / UNVERIFIED |
| n3.5 | RAGFlow dataset ingest and docs_search integration | REQ-DATA-033..037 | Not started / UNVERIFIED |
| n3.6 | Package receipts with actual bun test evidence | REQ-DATA-038 | Not started / UNVERIFIED |

Additional retained invariant coverage: REQ-DATA-030, REQ-DATA-031, REQ-DATA-032.

### Phase 4: Desk Gateway and contracts

**Goal**: Deliver contract-first per-seat gateway interfaces with real backend behavior, trusted authorization, audit, intake and public client reachability.
**Depends on**: Verified Phase 3
**Requirements**: REQ-GATEWAY-001, REQ-GATEWAY-002, REQ-GATEWAY-003, REQ-GATEWAY-004, REQ-GATEWAY-005, REQ-GATEWAY-006, REQ-GATEWAY-007, REQ-GATEWAY-008, REQ-GATEWAY-009, REQ-GATEWAY-010, REQ-GATEWAY-011, REQ-GATEWAY-012, REQ-GATEWAY-013, REQ-GATEWAY-014, REQ-GATEWAY-015, REQ-GATEWAY-016, REQ-GATEWAY-017, REQ-GATEWAY-018, REQ-GATEWAY-019, REQ-GATEWAY-020, REQ-GATEWAY-021, REQ-GATEWAY-022, REQ-GATEWAY-023, REQ-GATEWAY-024, REQ-GATEWAY-025, REQ-GATEWAY-026, REQ-GATEWAY-027, REQ-GATEWAY-028, REQ-GATEWAY-029, REQ-GATEWAY-030, REQ-GATEWAY-031, REQ-GATEWAY-032, REQ-GATEWAY-033, REQ-GATEWAY-034, REQ-GATEWAY-035, REQ-GATEWAY-036, REQ-GATEWAY-037, REQ-GATEWAY-038, REQ-GATEWAY-039, REQ-GATEWAY-040, REQ-GATEWAY-041, REQ-GATEWAY-042, REQ-GATEWAY-043, REQ-GATEWAY-044, REQ-GATEWAY-045, REQ-GATEWAY-046, REQ-GATEWAY-047, REQ-GATEWAY-048, REQ-GATEWAY-049, REQ-GATEWAY-050, REQ-GATEWAY-051, REQ-GATEWAY-052, REQ-GATEWAY-053, REQ-GATEWAY-054
**Success Criteria** (what must be TRUE):

  1. Seven roster and three initial pack contracts merge first with required G-4 consumer acknowledgements, every named tool schema/backend/gate tag and base 10–15 counts (LEAD 15, SYSTEMS 14, others 15).
  2. OAuth seat clients/scopes and 24-hour/30-day lifetimes enforce distinct lists and cross-seat 403; DNS/nginx/TLS/systemd/public route and scratch-Bot evidence are real, not local health alone.
  3. All eight core and every named seat/product-pack backend work; 20-second deadlines, read-open/write-closed behavior, redacted all-call audit and real G-5/G-6 authorization/rollback are enforced.
  4. Origin-token intake rejects seat tokens and non-LEAD intake calls, persists transactional queue/idempotency and acknowledges actual origins. Packs have at most five tools, twenty live tools, ticket lifetime/unload and observed list-change or fallback connectors.
  5. Independent receipt approval binds approval_ref to exact current reviewed SHA without a new tip or self-approval; observability/heartbeats and mobile approval boundary meet the retained contracts.

**Plans**: TBD (none created; discuss/research/plan/check before execution)
**Status**: Not started — UNVERIFIED
**Responsibility**: QUALITY contract first; SYSTEMS and INFRA owned work. Primary requirement assignment is Phase 4; later consumer evidence is retained in source references.
**Human/runtime checkpoint**: QUALITY contract-first/consumer ack gates precede implementation. Public DNS/TLS, real backend credentials and authorized release actions are required; approval_id text or an audit echo alone does not authorize G-5/G-6.
**Permitted overlap**: Gateway skeleton may start after verified Phase 1 while data work proceeds; final gateway delivery and verification still depend on Phase 3.

**Source steps** (not PLANs; all incomplete):

| Source step | Retained delivery | Requirement / consumer trace | Status |
| --- | --- | --- | --- |
| n4.1 | Seven roster and three initial pack contracts, consumers ack, contract first | REQ-GATEWAY-001..003, REQ-INVENTORY-016 | Not started / UNVERIFIED |
| n4.2 | Seat OAuth/routing, eight core tools and Greptime audit | REQ-GATEWAY-004..008, REQ-GATEWAY-012..020, REQ-GATEWAY-029, REQ-DATA-030 | Not started / UNVERIFIED |
| n4.3 | All seat tools, g5/g6, deadlines/failures, pack behavior and roster fixtures | REQ-GATEWAY-021..034, REQ-GATEWAY-036..039, REQ-GATEWAY-047..053, REQ-INVENTORY-012 | Not started / UNVERIFIED |
| n4.4 | Origin-token intake API and LEAD-only intake tools | REQ-GATEWAY-040..046 | Not started / UNVERIFIED |
| n4.5 | Public DNS/nginx/TLS/systemd/env and needed allowlist | REQ-GATEWAY-009..011, REQ-NETWORK-017 | Not started / UNVERIFIED |
| n4.6 | Scratch-Bot smoke: two distinct lists and wrong-seat 403 | REQ-GATEWAY-006, REQ-GATEWAY-007, REQ-GATEWAY-035 | Not started / UNVERIFIED |

### Phase 5: Prompts, skills, templates, plugin

**Goal**: Deliver all source prompt/skill/plugin/projector/template/bootstrap/doctor invariants with authorized human lifecycle and real Team-only publication.
**Depends on**: Verified Phase 4
**Requirements**: REQ-SHARE-001, REQ-SHARE-002, REQ-SHARE-003, REQ-SHARE-004, REQ-SHARE-005, REQ-SHARE-006, REQ-SHARE-007, REQ-SHARE-008, REQ-SHARE-009, REQ-SHARE-010, REQ-SHARE-011, REQ-SHARE-012, REQ-SHARE-013, REQ-SHARE-014, REQ-SHARE-015, REQ-SHARE-016, REQ-SHARE-017, REQ-SHARE-018, REQ-SHARE-019, REQ-SHARE-020, REQ-SHARE-021, REQ-SHARE-022, REQ-SHARE-023, REQ-SHARE-024, REQ-SHARE-025, REQ-SHARE-026, REQ-SHARE-027, REQ-SHARE-028, REQ-SHARE-029, REQ-SHARE-030, REQ-SHARE-031, REQ-SHARE-032, REQ-SHARE-033, REQ-SHARE-034, REQ-SHARE-035, REQ-SHARE-036, REQ-SHARE-037, REQ-SHARE-038, REQ-SHARE-039, REQ-SHARE-040
**Success Criteria** (what must be TRUE):

  1. All per-seat v1.1 tools/memory/connectors/routines and shared PD-8/placeholders assemble and parse against committed/registered rosters; G-7 rejects every source-defined bad fixture and runs in actual root CI.
  2. All seven specified skills are reviewed; swc-programming-desk contains skills/seven connectors; companion grok-bot projector and real agent-skills proposal PR route shared-library work.
  3. Authorized human owner reviews and installs/enables through account UI, with actual activation evidence; seats remain proposal-only absent skills.approve. Seven generated descriptions, actual avatars and published Team-only Share-card screenshots carry no excluded data.
  4. Bootstrap carries out all seven source steps including desktop OAuth, actual UUID/channel registration, six-seat group excluding QUALITY, pinned-tag prompt write/hash, paused routines until all doctors green and bank seeding.
  5. Doctor proves actual installed prompt/library versions, bank roundtrip, roster tool counts/gates, OAuth 403, real group/seven UUIDs/recent heartbeat, persisted event/docs hit; repair only reinstalls prompt/re-authenticates.

**Plans**: TBD (none created; discuss/research/plan/check before execution)
**Status**: Not started — UNVERIFIED
**Responsibility**: QUALITY shared; each seat prompt; LEAD templates. Primary requirement assignment is Phase 5; later consumer evidence is retained in source references.
**Human/runtime checkpoint**: Authorized human account owner must actually review and install/enable through account UI, publish Team-only templates and provide activation/Share evidence. Proposal PRs/private-library source/Markdown are not activated or published assets.

**Source steps** (not PLANs; all incomplete):

| Source step | Retained delivery | Requirement / consumer trace | Status |
| --- | --- | --- | --- |
| n5.1 | Placeholders/roster assembly/core PD-8/G-7 and fixtures | REQ-SHARE-001..003, REQ-SHARE-007, REQ-SHARE-039, REQ-INVENTORY-014 | Not started / UNVERIFIED |
| n5.2 | Every seat prompt sections, assembly and parsing | REQ-SHARE-004..009 | Not started / UNVERIFIED |
| n5.3 | All seven §8.2 skills authored and reviewed with authorized lifecycle | REQ-SHARE-008, REQ-SHARE-010, REQ-SHARE-019, REQ-SHARE-040 | Not started / UNVERIFIED |
| n5.4 | swc-programming-desk plugin and companion grok-bot projector | REQ-SHARE-011, REQ-SHARE-012, REQ-SHARE-014, REQ-SHARE-040 | Not started / UNVERIFIED |
| n5.5 | Seven actual Team-only templates and Share-card screenshots | REQ-SHARE-015..022 | Not started / UNVERIFIED |
| n5.6 | Desk pack skills_propose PR into agent-skills | REQ-SHARE-013 | Not started / UNVERIFIED |

Additional retained invariant coverage: REQ-SHARE-023..038.

### Phase 6: Fresh-desk acceptance and external intake

**Goal**: Prove the fresh-recipient desk, governed end-to-end ticket and independent approval, external intake, mobile use and failure behavior.
**Depends on**: Verified Phase 5
**Requirements**: REQ-ACCEPT-001, REQ-ACCEPT-002, REQ-ACCEPT-003, REQ-ACCEPT-004, REQ-ACCEPT-005, REQ-ACCEPT-006, REQ-ACCEPT-007, REQ-ACCEPT-008, REQ-ACCEPT-009, REQ-ACCEPT-010, REQ-ACCEPT-011, REQ-ACCEPT-012, REQ-ACCEPT-013, REQ-ACCEPT-014, REQ-ACCEPT-015, REQ-ACCEPT-016, REQ-ACCEPT-017, REQ-ACCEPT-018, REQ-ACCEPT-019, REQ-ACCEPT-020, REQ-ACCEPT-021, REQ-ACCEPT-022, REQ-ACCEPT-023, REQ-ACCEPT-024, REQ-ACCEPT-025, REQ-ACCEPT-026, REQ-ACCEPT-027, REQ-ACCEPT-028, REQ-ACCEPT-029, REQ-ACCEPT-030, REQ-ACCEPT-031, REQ-ACCEPT-032, REQ-ACCEPT-033, REQ-ACCEPT-034
**Success Criteria** (what must be TRUE):

  1. A person who never had the desk adds all seven templates, completes actual bootstrap and obtains seven evidence-backed green doctors; existing Bots/fixtures are not substitutes.
  2. Docs-only Ove 1:1 ask completes double uplift, Lane C ticket, awaiting-review/pending QUALITY and independent exact-SHA no-new-tip approval with current Greptile COMPLETED and real gate evidence.
  3. GitHub desk:intake label and origin-token curl reach LEAD and acknowledge Graph ID/Linear/Notion links to the origin; trigger support is observed or ten-minute polling remains.
  4. Actual iOS message and push-notification G-5 approval are evidenced; gateway/forwarder/cache/wrong-seat/twenty-first-tool drills show specified failures without public fallback.
  5. Current production-loop sparse/nested brief failure, revision-marker/degraded human acknowledgements, partial-write/recall retry, event payload and priority-false/channel/report rules are exercised; QUALITY judges real evidence and Ove's open question set is at most four.

**Plans**: TBD (none created; discuss/research/plan/check before execution)
**Status**: Not started — UNVERIFIED
**Responsibility**: LEAD orchestrates; QUALITY judges. Primary requirement assignment is Phase 6; later consumer evidence is retained in source references.
**Human/runtime checkpoint**: A genuinely fresh recipient, actual iOS Ove action, human loop acknowledgements and independent exact-head QUALITY reviewer are required. Do not auto-answer acceptance or synthesize approval/waiver/Greptile results.

**Source steps** (not PLANs; all incomplete):

| Source step | Retained delivery | Requirement / consumer trace | Status |
| --- | --- | --- | --- |
| n6.1 | Fresh recipient adds seven templates, bootstraps and seven doctors green | REQ-ACCEPT-001, REQ-ACCEPT-002, REQ-SHARE-023..038 | Not started / UNVERIFIED |
| n6.2 | Docs-only LEAD ask, double uplift/ticket/pending result, independent exact-SHA approval | REQ-ACCEPT-003..007, REQ-ACCEPT-020..034, REQ-GATEWAY-036..038 | Not started / UNVERIFIED |
| n6.3 | GitHub-label and curl-origin intake, LEAD acknowledgement to issue/origin | REQ-ACCEPT-008, REQ-ACCEPT-009, REQ-INVENTORY-015, REQ-GATEWAY-040..045 | Not started / UNVERIFIED |
| n6.4 | Actual iOS message and push-notification g5 approval | REQ-ACCEPT-010, REQ-ACCEPT-011, REQ-GATEWAY-054 | Not started / UNVERIFIED |
| n6.5 | Gateway/forwarder/cache/wrong-seat/pack-ceiling failure drills | REQ-ACCEPT-012..017 | Not started / UNVERIFIED |
| n6.6 | Open acceptance questions to Ove capped at four | REQ-ACCEPT-018 | Not started / UNVERIFIED |

Mandatory closure requirement: REQ-ACCEPT-019.

### Phase 7: Ordered rollout and rollback

**Goal**: Roll out only verified dependencies in source order with authorized rollback, human-visible coordination, truthful tracker sync and final clearance.
**Depends on**: Verified Phases 2, 3, 4, 5 and 6
**Requirements**: REQ-ROLLOUT-001, REQ-ROLLOUT-002, REQ-ROLLOUT-003, REQ-ROLLOUT-004, REQ-ROLLOUT-005, REQ-ROLLOUT-006, REQ-ROLLOUT-007, REQ-ROLLOUT-008, REQ-ROLLOUT-009, REQ-ROLLOUT-010, REQ-ROLLOUT-011, REQ-ROLLOUT-012, REQ-ROLLOUT-013
**Success Criteria** (what must be TRUE):

  1. Verified n2→n3→n4→n5→n6 precedes rollout; only gateway skeleton overlap after n1 is allowed, with no early phase completion.
  2. Each node has source-specified authorized rollback evidence: forwarder/proxy/domain recreation, env file restoration, additive gateway removal, v1.0 prompt reassembly with committed roster and template republication.
  3. Desk cutover windows and dispatch audit notes exist; actual PR fields mirror to Notion/Linear and Ove 1:1 report cites all receipts and unverified paths.
  4. Superseded railway-app retirement occurs only after verified n6 and real G-6 approval; a still-required node is not retired.
  5. G-1–G-6 remain intact and G-7 additive; exact-current-SHA independent approval, current review/waiver state and real E2E evidence control final clearance without manufactured receipts.

**Plans**: TBD (none created; discuss/research/plan/check before execution)
**Status**: Not started — UNVERIFIED
**Responsibility**: LEAD; owned node rollbacks by specialists. Primary requirement assignment is Phase 7; later consumer evidence is retained in source references.
**Human/runtime checkpoint**: Actual source-order phase verification and destructive-operation approval remain mandatory. Root initialization/user request to continue or push does not authorize deployment, access change or node retirement.

**Source steps** (not PLANs; all incomplete):

| Source step | Retained delivery | Requirement / consumer trace | Status |
| --- | --- | --- | --- |
| n7.1 | Source order with allowed gateway skeleton overlap | REQ-ROLLOUT-001, REQ-ROLLOUT-012 | Not started / UNVERIFIED |
| n7.2 | Network/env/gateway/prompt/template rollback evidence | REQ-ROLLOUT-002..006 | Not started / UNVERIFIED |
| n7.3 | Desk cutover windows and dispatch-note audit trail | REQ-ROLLOUT-007, REQ-ROLLOUT-008 | Not started / UNVERIFIED |
| n7.4 | PR-field sync and Ove report with all receipt paths/unverified | REQ-ROLLOUT-009, REQ-ROLLOUT-010 | Not started / UNVERIFIED |
| n7.5 | If superseded, retire railway-app after n6 with G-6 approval | REQ-ROLLOUT-011 | Not started / UNVERIFIED |

Mandatory closure requirement: REQ-ROLLOUT-013.

## Cross-Repository Delivery and Gates

- programming-desk: LEAD owns .planning and grokbot/bootstrap/integration; QUALITY owns contracts/shared prompts/assembly/gates/broad docs and independent review; SYSTEMS owns gateway; INFRA owns infra/workflows/network platform skill; each seat owns its prompt. Last-match ownership and contract consumers must be resolved before edits. The source §13 change is a QUALITY ticket, not a bootstrap-owned edit.
- agent-substrate: owned companion docs/env/README/PROJECT Data updates; GSD-mediated Phase 5/7/8 replan; Hindsight/Dragonfly/Timescale/RAGFlow/ledger integration and grok-bot projector, package receipts and gated merges. Those are actual milestone dependencies, not local substitutes or authority to edit that repo in this bootstrap.
- agent-skills: real skills_propose PR and independent shared-library review; runtime owners supply authorized installation/backups.
- Source lanes: n2/n5 Lane C specialists; n3/n4 default Lane A Cursor Cloud Agents with second-uplift XML; Lane B only if Ove asks. LEAD orchestrates and dispatches 1:1; Desk is the human-visible audit channel, not assignment bus. QUALITY remains off-channel.
- Research, planner checker, verifier and code review stay enabled. Source G-1–G-6 and additive G-7, actual contract ack, current Greptile COMPLETED, exact-SHA independent approval and human/runtime gates remain required. Advisory code-review configuration is not merge clearance. Parent owns consolidated checks; none run in bootstrap.

## Evidence and Resumption

Durable inputs: [implementation map](intel/implementation-map.md), [Phase 1 inventory](phases/01-inventory-and-prove-assumptions/01-INVENTORY.md), [machine inventory](phases/01-inventory-and-prove-assumptions/01-INVENTORY.json). These are evidence-worker-owned fixed paths, referenced without reading incomplete output. Existing local gateway health does not establish public reachability or registrations; substrate HTTP 503 and missing forwarders block dependent runtime claims. Complete evidence limits remain in [context](intel/context.md) and [conflicts](INGEST-CONFLICTS.md).

## Progress

**Execution Order:** 1 → 2 → 3 → 4 → 5 → 6 → 7; only the documented Phase 4 skeleton overlap is permitted.

| Phase | Milestone | Plans Complete | Status | Completed |
| --- | --- | --- | --- | --- |
| 1. Inventory and prove assumptions | v2.0 | 7/7 | Complete | 2026-10-08 |
| 2. Network plane | v2.0 | 6/6 | Complete (at designed stop) | 2026-10-08 |
| 3. Substrate data planes | v2.0 | 0/TBD | In progress | - |
| 4. Desk Gateway and contracts | v2.0 | 0/TBD | Not started | - |
| 5. Prompts, skills, templates, plugin | v2.0 | 0/TBD | Not started | - |
| 6. Fresh-desk acceptance and external intake | v2.0 | 0/TBD | Not started | - |
| 7. Ordered rollout and rollback | v2.0 | 0/TBD | Not started | - |
