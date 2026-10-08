# Requirements: Programming Desk v2

**Defined:** 2026-10-08
**Milestone:** v2.0 — Desk v2
**Core Value:** A fresh team can install a seven-seat desk whose work, tools, memory and approvals are independently evidenced and safely governed.

## Current Milestone Requirements

All 217 stable REQ IDs remain active and unchecked. Every ID has exactly one primary delivery phase; source-step references may identify later consumers or prerequisites, not additional primary phases. AC IDs replace REQ- with AC-. No source file, historical receipt, fixture or supplied observation establishes completion.

Source: [approved plan](../docs/upgrade-plan-desk-v2.md) §§5–13 and Appendices A–D; [current governance](../docs/desk-operating-model.md). Complete tool, schema, bootstrap and doctor semantics: [constraints](intel/constraints.md). Original discrepancy provenance and explicit Create planning setup routing: [conflict record](INGEST-CONFLICTS.md).

### INVENTORY — Phase 1: Inventory and prove assumptions

- [x] **REQ-INVENTORY-001**: Given the operator's original ask, when LEAD performs the first uplift, then ORIGINAL contains the verbatim §1 block, not a paraphrase.
  - Source: P §1; §12 kickoff L314; source step / responsibility: n1 kickoff; LEAD; acceptance ID: AC-INVENTORY-001.
- [x] **REQ-INVENTORY-002**: Given the selected full graph, when kickoff is recorded, then all seven nodes and their 41 source steps have traceable node issues and step sub-issues in the Notion Agent Task Graph and Linear Spectrum Web Co.
  - Source: P §12 kickoff L314; G Flow 3–4; source step / responsibility: n1 kickoff; LEAD; acceptance ID: AC-INVENTORY-002.
- [x] **REQ-INVENTORY-003**: Given created tracker rows, when the second uplift is dispatched, then its ISSUES section contains the live Notion/Linear URLs for the assigned node and steps.
  - Source: P §12 kickoff L314; G Flow 5–6; source step / responsibility: n1 kickoff; LEAD; acceptance ID: AC-INVENTORY-003.
- [x] **REQ-INVENTORY-004**: Given access to Ove's two Railway projects, when inventory is recorded, then actual service names, ports and environments are recorded for GreptimeDB, TimescaleDB, DragonflyDB, Hindsight and RAGFlow; provisional defaults are labelled until confirmed.
  - Source: P §12 n1.1; §5 mapping table; §13 service names; source step / responsibility: n1.1; LEAD → INFRA; acceptance ID: AC-INVENTORY-004.
- [x] **REQ-INVENTORY-005**: Given the railway-app tailnet node, when its identity is investigated, then its Railway project, role and advertised routes are recorded with evidence rather than inferred from online status.
  - Source: P §12 n1.2; §5 railway-app; §13 railway-app; source step / responsibility: n1.2; INFRA; acceptance ID: AC-INVENTORY-005.
- [x] **REQ-INVENTORY-006**: Given an actual Bot computer, when its UUID is read, then the receipt names the exact agent-data path and observed UUID.
  - Source: P §12 n1.3; §9.2 step 3; §13 Bot path; source step / responsibility: n1.3; LEAD / participating Bot; acceptance ID: AC-INVENTORY-006.
- [x] **REQ-INVENTORY-007**: Given that Bot's own SYSTEM_PROMPT.xml, when write access is proved, then the result and exact writable path are recorded; a cited architecture path alone is not proof.
  - Source: P §12 n1.3; §13 Bot path; source step / responsibility: n1.3; LEAD / participating Bot; acceptance ID: AC-INVENTORY-007.
- [x] **REQ-INVENTORY-008**: Given Grok Bot's MCP client, when a pack changes the tools list, then observed notification support is recorded, or the fallback connector path is selected on observed non-support.
  - Source: P §12 n1.4; §7.4; §13 tools/list_changed; source step / responsibility: n1.4; LEAD / SYSTEMS; acceptance ID: AC-INVENTORY-008.
- [x] **REQ-INVENTORY-009**: Given the Cursor team's network settings, when inspected, then open versus Team-allowlist-only policy is recorded and the gateway allowlist need is identified.
  - Source: P §12 n1.5; §5 Bot computers; §13 network policy; source step / responsibility: n1.5; INFRA; acceptance ID: AC-INVENTORY-009.
- [x] **REQ-INVENTORY-010**: Given the team's plan, when inventoried, then its tier is recorded without assuming Enterprise Team Setup is available.
  - Source: P §12 n1.5; §13 plan tier; source step / responsibility: n1.5; LEAD; acceptance ID: AC-INVENTORY-010.
- [x] **REQ-INVENTORY-011**: Given n1 findings, when the plan's assumptions are updated, then §13 distinguishes observed results, unresolved assumptions and unexercised behavior with source evidence.
  - Source: P §12 n1.6; §13; source step / responsibility: n1.6; LEAD → QUALITY docs ticket; acceptance ID: AC-INVENTORY-011.
- [x] **REQ-INVENTORY-012**: Given the mobile release integrations, when credentials are inventoried, then availability and ownership of Play Developer and App Store Connect credentials are recorded without disclosing their values to Bots or templates.
  - Source: P §13 Play/App Store credentials; §7.1 upstreams; source step / responsibility: n4.3 prerequisite; INFRA; acceptance ID: AC-INVENTORY-012.
- [x] **REQ-INVENTORY-013**: Given Railway Hindsight, when preparing to store data, then its actual version and embedding dimensions are established before the first stored data; the cited template version is not asserted as the live version.
  - Source: P §13 Hindsight version/model; §12 n3.2; source step / responsibility: n3.2 prerequisite; SYSTEMS in agent-substrate; acceptance ID: AC-INVENTORY-013.
- [x] **REQ-INVENTORY-014**: Given the PR gate workflow, when CI activation is claimed, then an active root .github/workflows/gates.yml is evidenced rather than inferred from ci/.github/workflows/gates.yml or the historical inventory.
  - Source: P §11 CI activation; §13 GitHub Actions; source step / responsibility: n5.1; INFRA / QUALITY; acceptance ID: AC-INVENTORY-014.
- [x] **REQ-INVENTORY-015**: Given the team's Cursor integrations, when intake event triggers are evaluated, then their actual availability is recorded and the ten-minute polling floor remains when triggers are unavailable.
  - Source: P §13 desk-intake-poll; §8.1 item 7; §10 Slack; source step / responsibility: n6.3; LEAD; acceptance ID: AC-INVENTORY-015.
- [x] **REQ-INVENTORY-016**: Given a new Desk v2 path, when work is assigned, then ownership already covers it with last-match-wins resolution and declared contract consumers; an unowned path fails G-1.
  - Source: P §11 ownership; Appendix A; opening policy; source step / responsibility: n1 / before n4–n5 path creation; QUALITY; acceptance ID: AC-INVENTORY-016.

### NETWORK — Phase 2: Network plane

- [ ] **REQ-NETWORK-001**: Given confirmed Ultrathink/production service names, when its forwarder is deployed or adopted, then the five mapped ports 4000, 4001, 4003, 5432 and 6379 reach their specified Greptime, Timescale and Dragonfly services through the tailnet machine name.
  - Source: P §12 n2.1; §5 mapping table; source step / responsibility: n2.1; INFRA; acceptance ID: AC-NETWORK-001.
- [ ] **REQ-NETWORK-002**: Given confirmed Agent Substrate/production service names, when its forwarder is deployed or adopted, then Hindsight 8888 and RAGFlow API 9380 are reachable through the tailnet machine name; RAGFlow web port 80 remains an explicitly optional mapping.
  - Source: P §12 n2.2; §5 mapping table; source step / responsibility: n2.2; INFRA; acceptance ID: AC-NETWORK-002.
- [ ] **REQ-NETWORK-003**: Given each Railway forwarder, when it restarts, then its machine identity persists on its volume and its mapping remains project/environment-specific.
  - Source: P §5 mechanism; source step / responsibility: n2.1–2; INFRA; acceptance ID: AC-NETWORK-003.
- [ ] **REQ-NETWORK-004**: Given both forwarders, when tailnet enrollment is configured, then they have tag:railway-forwarder, disabled key expiry and a reusable tagged non-ephemeral auth key; no key value enters a receipt.
  - Source: P §5 ACL; §12 n2.1; source step / responsibility: n2.1–3; INFRA; acceptance ID: AC-NETWORK-004.
- [ ] **REQ-NETWORK-005**: Given the user-approved VPS plus Ove's Mac mini and XPS scope, when ACLs are applied, then tag:vps and those tag:admin members reach only exact mapped forwarder ports and all other principals are denied.
  - Source: P §5 ACL; §12 n2.3; RW-02; source step / responsibility: n2.3; INFRA; acceptance ID: AC-NETWORK-005.
- [ ] **REQ-NETWORK-006**: Given the VPS, when each mapped port is probed over the tailnet name, then the receipt records the protocol-level result for every exercised mapping.
  - Source: P §12 n2.3; §5 evidence; source step / responsibility: n2.3; INFRA; acceptance ID: AC-NETWORK-006.
- [ ] **REQ-NETWORK-007**: Given the Mac mini administrative path, when the mapped ports are probed, then its permitted access is evidenced separately from VPS results.
  - Source: P §12 n2.3; §5 goal; source step / responsibility: n2.3; INFRA / Ove's Mac mini; acceptance ID: AC-NETWORK-007.
- [ ] **REQ-NETWORK-008**: Given verified forwarders, when the substrate environment is cut over, then all five service URLs use the specified MagicDNS forwarder hosts, not public proxies or public DB domains.
  - Source: P §12 n2.4; §5 VPS cutover; source step / responsibility: n2.4; INFRA; acceptance ID: AC-NETWORK-008.
- [ ] **REQ-NETWORK-009**: Given the cut-over substrate environment, when substrate-mcp is restarted, then /brief is verified against that running configuration.
  - Source: P §12 n2.4; source step / responsibility: n2.4; INFRA; acceptance ID: AC-NETWORK-009.
- [ ] **REQ-NETWORK-010**: Given the restarted substrate, when events_emit is invoked, then its recorded result proves the post-cutover event path rather than merely service startup.
  - Source: P §12 n2.4; source step / responsibility: n2.4; INFRA; acceptance ID: AC-NETWORK-010.
- [ ] **REQ-NETWORK-011**: Given a recorded G-6 approval and re-create rollback, when the TimescaleDB TCP proxy is retired, then proxy removal is evidenced by the Railway CLI or dashboard.
  - Source: P §12 n2.5; §5 retire public exposure; source step / responsibility: n2.5; INFRA / recorded G-6 approver; acceptance ID: AC-NETWORK-011.
- [ ] **REQ-NETWORK-012**: Given a recorded G-6 approval and re-create rollback, when the Greptime public domain is retired, then domain removal is evidenced by the Railway CLI or dashboard.
  - Source: P §12 n2.5; §5 retire public exposure; source step / responsibility: n2.5; INFRA / recorded G-6 approver; acceptance ID: AC-NETWORK-012.
- [ ] **REQ-NETWORK-013**: Given public database exposure, when retirement is requested, then it occurs only after the replacement forwarder/cutover path is verified.
  - Source: P D-2; §5 retire public exposure / railway-app; source step / responsibility: n2.5; INFRA; acceptance ID: AC-NETWORK-013.
- [ ] **REQ-NETWORK-014**: Given hindsight-ui browser access, when exposure is selected, then it is kept on an access-key-protected Railway domain only if Ove requests non-tailnet browser access; otherwise administration uses the Mac mini tailnet path.
  - Source: P §5 retire public exposure; source step / responsibility: n2.5; Ove → INFRA; acceptance ID: AC-NETWORK-014.
- [ ] **REQ-NETWORK-015**: Given evidence railway-app is already a suitable forwarder, when provisioning is selected, then it is adopted without creating a duplicate; an unidentified node is not silently assumed suitable.
  - Source: P §5 railway-app; §12 n1.2 / n7.5; source step / responsibility: n1.2 decision feeding n2; INFRA; acceptance ID: AC-NETWORK-015.
- [ ] **REQ-NETWORK-016**: Given a Grok Bot, when connecting to Desk v2, then it uses normal HTTPS egress to the public gateway and does not join the tailnet or hold database credentials.
  - Source: P D-2; §5 Bot computers; source step / responsibility: n2 / n4; INFRA; acceptance ID: AC-NETWORK-016.
- [ ] **REQ-NETWORK-017**: Given Team allowlist only, when the gateway is enabled, then desk.swcstudio.space is included in the team's allowlist.
  - Source: P §5 Bot computers; §12 n4.5; source step / responsibility: n4.5; INFRA; acceptance ID: AC-NETWORK-017.
- [ ] **REQ-NETWORK-018**: Given emergency Mac-mini-routed egress, when documented, then it is INFRA-only and states the dependency on the Mac mini remaining awake.
  - Source: P §5 Bot computers; source step / responsibility: n2 documentation; INFRA; acceptance ID: AC-NETWORK-018.
- [ ] **REQ-NETWORK-019**: Given plaintext mapped service ports, when used, then their hop is WireGuard-encrypted inside the tailnet and Hindsight/RAGFlow still require their bearer keys.
  - Source: P §5 VPS cutover; source step / responsibility: n2.4; INFRA; acceptance ID: AC-NETWORK-019.
- [ ] **REQ-NETWORK-020**: Given n2 execution, when its receipt is published, then it contains tailscale status, port-probe evidence, removal evidence, rollback and an unverified list covering every unexercised path.
  - Source: P §12 n2.6; §5 evidence; source step / responsibility: n2.6; INFRA; acceptance ID: AC-NETWORK-020.
- [ ] **REQ-NETWORK-021**: Given the approved VPS plus Mac mini and XPS scope, when network access is verified, then all three permitted device paths are evidenced and access outside the exact mapped ports remains denied; design approval alone is not probe evidence.
  - Source: P §5 goal L95; RW-02 overrides original Mac-mini-only wording; source step / responsibility: n2.3; INFRA; acceptance ID: AC-NETWORK-021.
- [ ] **REQ-NETWORK-022**: Given Ove's Mac mini and XPS as the approved tag:admin members, when ACL membership is configured, then both receive the same exact-port grants alongside the VPS, with deny-by-default for every other principal.
  - Source: P §5 ACL L104; RW-02; source step / responsibility: n2.3; INFRA; acceptance ID: AC-NETWORK-022.

### DATA — Phase 3: Substrate data planes

- [ ] **REQ-DATA-001**: Given the companion policy document, when docs/data-planes.md is delivered, then it records the §6 stores, schemas, bank names, writers, retention and forbidden data classes.
  - Source: P §6 companion changes; Appendix D; §12 n3.1; source step / responsibility: n3.1; SYSTEMS in agent-substrate; acceptance ID: AC-DATA-001.
- [ ] **REQ-DATA-002**: Given companion networking documentation, when docs/railway-tailscale.md is delivered, then it records forwarders, ACLs, cutover and rollback.
  - Source: P §6 companion changes; Appendix D; §12 n3.1; source step / responsibility: n3.1; SYSTEMS / INFRA in agent-substrate; acceptance ID: AC-DATA-002.
- [ ] **REQ-DATA-003**: Given .env.example, when the data-plane contract changes, then it contains HINDSIGHT_URL, HINDSIGHT_API_KEY, HINDSIGHT_BANK_PREFIX, DRAGONFLY_URL, SUBSTRATE_TOKEN_DESK_GATEWAY and tailnet hosts, with AGENTMEMORY_* removed and no credential values.
  - Source: P §6 companion changes; Appendix D; source step / responsibility: n3.1; agent-substrate owner; acceptance ID: AC-DATA-003.
- [ ] **REQ-DATA-004**: Given the companion repository's data summaries, when docs are upgraded, then README.md and the PROJECT.md Data section describe the five-service policy instead of the obsolete memory/cache plan. These are external deliverables, not permitted writes here.
  - Source: P §6 companion changes; Appendix D; source step / responsibility: n3.1; agent-substrate owner; acceptance ID: AC-DATA-004.
- [ ] **REQ-DATA-005**: Given the companion data policy, when substrate phases are replanned, then Phase 5 includes tailnet RAGFlow docs, Phase 7 uses Hindsight, and Phase 8 is Dragonfly cache-only through GSD tooling rather than a hand-edited ROADMAP.
  - Source: P §6 companion changes; source step / responsibility: n3.1; agent-substrate GSD owner; acceptance ID: AC-DATA-005.
- [ ] **REQ-DATA-006**: Given the companion docs PR, when integration depends on it, then its actual gated merge is evidenced; file existence in programming-desk does not satisfy the cross-repo dependency.
  - Source: P §12 n3.1; source step / responsibility: n3.1; companion PR owners / independent reviewers; acceptance ID: AC-DATA-006.
- [ ] **REQ-DATA-007**: Given memory_write, when a supported fact is retained, then the substrate adapter routes it to Hindsight retain in the authorized pd-* bank while keeping the tenant key on the substrate.
  - Source: P §6 memory; §12 n3.2; source step / responsibility: n3.2; SYSTEMS in agent-substrate; acceptance ID: AC-DATA-007.
- [ ] **REQ-DATA-008**: Given memory_search, when recall is requested, then the substrate adapter uses Hindsight recall with the authorized bank scope.
  - Source: P §6 memory; §12 n3.2; source step / responsibility: n3.2; SYSTEMS in agent-substrate; acceptance ID: AC-DATA-008.
- [ ] **REQ-DATA-009**: Given a seat identity, when bank access is exercised, then all seats may read pd-desk, only LEAD/QUALITY may write pd-desk, a seat writes only pd-<seat>, and LEAD's recall additionally includes pd-lead-reports.
  - Source: P §6 memory; §7.2 memory tools; source step / responsibility: n3.2; SYSTEMS; acceptance ID: AC-DATA-009.
- [ ] **REQ-DATA-010**: Given a retain request, when it lacks a receipt path or source URL or contains prohibited secrets/unverified claims, then it is refused or redacted according to D-04 before retaining prohibited content.
  - Source: P §6 memory; §7.2 desk_memory_retain; §12 n3.2; source step / responsibility: n3.2; SYSTEMS; acceptance ID: AC-DATA-010.
- [ ] **REQ-DATA-011**: Given the Hindsight adapter, when health/version compatibility is checked, then the /health version gate and pre-established embedding dimensions control readiness before storing data.
  - Source: P §12 n3.2; §13 Hindsight version/model; source step / responsibility: n3.2; SYSTEMS; acceptance ID: AC-DATA-011.
- [ ] **REQ-DATA-012**: Given retained verified memory, when retention is applied, then the facts are retained forever rather than assigned a cache TTL.
  - Source: P §6 memory retention; source step / responsibility: n3.2; SYSTEMS; acceptance ID: AC-DATA-012.
- [ ] **REQ-DATA-013**: Given the user-selected weekly reflection cadence, when Hindsight reflection is configured and exercised, then verified retained facts produce mental models weekly, with no nightly or split-bank schedule.
  - Source: P §6 memory data-class cell L127; RW-01 overrides original nightly wording; source step / responsibility: n3.2; SYSTEMS; acceptance ID: AC-DATA-013.
- [ ] **REQ-DATA-014**: Given weekly reflect/pruning into mental models, when the memory policy and hindsight-memory skill are delivered, then both document the same weekly discipline, retaining verified facts forever and recording actual scheduled execution separately.
  - Source: P §6 memory retention cell L127; §8.2 hindsight-memory; RW-01; source step / responsibility: n3.2 / n5.3; SYSTEMS / QUALITY; acceptance ID: AC-DATA-014.
- [ ] **REQ-DATA-015**: Given the Claude Code local hindsight stdio entry, when the substrate adapter replaces it, then the old entry is backed up before retirement.
  - Source: P §12 n3.2; §6 memory; source step / responsibility: n3.2; SYSTEMS / external runtime owner; acceptance ID: AC-DATA-015.
- [ ] **REQ-DATA-016**: Given Hermes memory configuration, when the shared Hindsight path replaces its provider, then its prior configuration is backed up and memory.provider becomes none.
  - Source: P §12 n3.2; §6 memory; source step / responsibility: n3.2; SYSTEMS / Hermes runtime owner; acceptance ID: AC-DATA-016.
- [ ] **REQ-DATA-017**: Given a Dragonfly restart or loss, when its data is discarded, then no durable session, queue, pub/sub, lock or irreplaceable record is lost because Dragonfly holds cache-only data.
  - Source: P §6 Dragonfly; §12 n3.3; source step / responsibility: n3.3; SYSTEMS; acceptance ID: AC-DATA-017.
- [ ] **REQ-DATA-018**: Given a cached brief, when its cache age exceeds five minutes, then it is no longer served as a live cache entry.
  - Source: P §6 Dragonfly; §7.2 desk_brief; source step / responsibility: n3.3; SYSTEMS; acceptance ID: AC-DATA-018.
- [ ] **REQ-DATA-019**: Given docs_search/recall cache entries, when their age exceeds ten minutes, then they are no longer served as live cache entries.
  - Source: P §6 Dragonfly; source step / responsibility: n3.3; SYSTEMS; acceptance ID: AC-DATA-019.
- [ ] **REQ-DATA-020**: Given per-seat rate-limit counters, when their retention exceeds one hour, then their cache entries expire.
  - Source: P §6 Dragonfly; source step / responsibility: n3.3; SYSTEMS; acceptance ID: AC-DATA-020.
- [ ] **REQ-DATA-021**: Given an idempotency cache mirror, when twenty-four hours pass, then the mirror may expire without replacing the thirty-day Timescale processed-key record.
  - Source: P §6 Dragonfly / Timescale; source step / responsibility: n3.3; SYSTEMS; acceptance ID: AC-DATA-021.
- [ ] **REQ-DATA-022**: Given Dragonfly is unreachable, when a cache-backed read is made, then it falls through to its authoritative source and returns the same answer uncached.
  - Source: P §6 Dragonfly; §12 n3.3 / n6.5; source step / responsibility: n3.3; SYSTEMS; acceptance ID: AC-DATA-022.
- [ ] **REQ-DATA-023**: Given Timescale migrations, when applied, then desk_intake, desk_claims, desk_idempotency, desk_receipts, seat_roster and tool_pack_state exist alongside the graph index/node/step coordination surfaces.
  - Source: P §6 coordination; §12 n3.4; source step / responsibility: n3.4; SYSTEMS in agent-substrate; acceptance ID: AC-DATA-023.
- [ ] **REQ-DATA-024**: Given concurrent intake claimants, when an intake row is drained, then the Timescale queue uses transactional FOR UPDATE SKIP LOCKED rather than a Dragonfly queue or lock.
  - Source: P §6 coordination; source step / responsibility: n3.4; SYSTEMS; acceptance ID: AC-DATA-024.
- [ ] **REQ-DATA-025**: Given a Graph ID claim, when its lifetime is recorded, then desk_claims holds an expiring per-Graph-ID claim row.
  - Source: P §6 coordination; source step / responsibility: n3.4; SYSTEMS; acceptance ID: AC-DATA-025.
- [ ] **REQ-DATA-026**: Given a processed idempotency key, when it is retained, then Timescale holds the processed-key set for thirty days; the cache mirror is not the record.
  - Source: P §6 coordination; source step / responsibility: n3.4; SYSTEMS; acceptance ID: AC-DATA-026.
- [ ] **REQ-DATA-027**: Given coordination/index rows and aggregates, when retention runs, then rows survive while their Graph ID is open plus ninety days and aggregates survive one year.
  - Source: P §6 coordination retention; source step / responsibility: n3.4; SYSTEMS; acceptance ID: AC-DATA-027.
- [ ] **REQ-DATA-028**: Given seat heartbeat/tool-call telemetry, when stored, then seat_heartbeat and tool_calls_1m hypertables and continuous aggregates supply the specified rollups.
  - Source: P §6 coordination; §12 n3.4; source step / responsibility: n3.4; SYSTEMS; acceptance ID: AC-DATA-028.
- [ ] **REQ-DATA-029**: Given a shipped-work claim, when its source of truth is identified, then GitHub remains the record; rebuildable indexes and tracker mirrors are not promoted to shipment truth, and the intake queue is the stated non-rebuildable exception.
  - Source: P §4 rule 4; §6 coordination; source step / responsibility: n3; all owners; acceptance ID: AC-DATA-029.
- [ ] **REQ-DATA-030**: Given tool calls, receipts, dispatches, intake or seat heartbeats, when an event is recorded, then Greptime agent_events is append-only with hash/prev chain and redacted content, not secrets or full transcripts.
  - Source: P §6 events; §7.1 audit; source step / responsibility: n3 / n4; SYSTEMS; acceptance ID: AC-DATA-030.
- [ ] **REQ-DATA-031**: Given hourly event ledger roots, when anchored, then packages/ledger anchors a Merkle root to Solana devnet.
  - Source: P §6 events; source step / responsibility: n3; agent-substrate ledger owner; acceptance ID: AC-DATA-031.
- [ ] **REQ-DATA-032**: Given event retention, when data ages beyond 180 hot days, then it is exported rather than claimed as indefinitely hot storage.
  - Source: P §6 events retention; source step / responsibility: n3; agent-substrate owner; acceptance ID: AC-DATA-032.
- [ ] **REQ-DATA-033**: Given document ingestion, when datasets are selected, then programming-desk, agent-substrate and one dataset per product repository cover KanbanOS, Desk Lanes, ClippyOS and Auctioning docs/skills/contracts/ADRs.
  - Source: P §6 documents; source step / responsibility: n3.5; SYSTEMS / product repo owners; acceptance ID: AC-DATA-033.
- [ ] **REQ-DATA-034**: Given a merge to main, when document ingestion runs through POST /v1/docs/ingest, then RAGFlow is re-ingested and keeps the last five dataset versions.
  - Source: P §6 documents; §12 n3.5; source step / responsibility: n3.5; SYSTEMS / GitHub ingest workflow owner; acceptance ID: AC-DATA-034.
- [ ] **REQ-DATA-035**: Given docs_search, when repository documents are retrieved, then RAGFlow supplies heading-aware chunks using the stated TEI bge-small embedding plan without requiring a chat model.
  - Source: P §6 documents; §12 n3.5; source step / responsibility: n3.5; SYSTEMS; acceptance ID: AC-DATA-035.
- [ ] **REQ-DATA-036**: Given RAGFlow input, when indexed, then secrets, receipts and transcripts are excluded; receipts remain evidence rather than documents.
  - Source: P §6 documents; source step / responsibility: n3.5; SYSTEMS; acceptance ID: AC-DATA-036.
- [ ] **REQ-DATA-037**: Given a seat's docs or memory call, when executed, then it uses the substrate or gateway rather than raw Hindsight/RAGFlow endpoints or user-hindsight/user-ragflow credentials.
  - Source: P §4 rule 3; §6 memory; G production loop point 7; source step / responsibility: n3 / n4; SYSTEMS / every seat; acceptance ID: AC-DATA-037.
- [ ] **REQ-DATA-038**: Given each changed substrate package, when its receipt is prepared, then actual bun test evidence is recorded with package scope and unverified limits. No such command was executed by this ingest worker.
  - Source: P §12 n3.6; source step / responsibility: n3.6; SYSTEMS in agent-substrate; future verification by parent; acceptance ID: AC-DATA-038.

### GATEWAY — Phase 4: Desk Gateway and contracts

- [x] **REQ-GATEWAY-001**: Given the seven seat contracts, when published, then each roster declares tool names, JSON schemas, backend, gate tags and consumers with contract_surface=true.
  - Source: P §7.1 contract; §11; §12 n4.1; source step / responsibility: n4.1; QUALITY; acceptance ID: AC-GATEWAY-001.
- [x] **REQ-GATEWAY-002**: Given the first pack contracts, when published, then kanbanos, desklanes and clippyos declare their application-specific tools and record required consumer acknowledgements.
  - Source: P §7.4; §11; §12 n4.1; source step / responsibility: n4.1; QUALITY / WEB, ANDROID, IOS consumers; acceptance ID: AC-GATEWAY-002.
- [x] **REQ-GATEWAY-003**: Given gateway implementation or a breaking roster/pack change, when it is integrated, then the contract PR has merged first and G-4 acknowledgements cover affected seat consumers.
  - Source: P §7.1 contract; §11 contracts; §12 n4.1; source step / responsibility: n4.1 before n4.2–3; QUALITY / consumers; acceptance ID: AC-GATEWAY-003.
- [x] **REQ-GATEWAY-004**: Given a seat connector, when OAuth completes, then its own desk-<seat> client grants only seat:<name> for that seat's /mcp/<seat> endpoint.
  - Source: P §7.1 auth; §12 n4.2; source step / responsibility: n4.2; SYSTEMS; acceptance ID: AC-GATEWAY-004.
- [x] **REQ-GATEWAY-005**: Given issued OAuth credentials, when token lifetimes are inspected, then access tokens last twenty-four hours and refresh credentials last thirty days.
  - Source: P §7.1 auth; source step / responsibility: n4.2; SYSTEMS; acceptance ID: AC-GATEWAY-005.
- [x] **REQ-GATEWAY-006**: Given a token for seat A, when used on seat B's endpoint, then the gateway returns 403.
  - Source: P §7.1 per-seat surface; §12 n4.6; source step / responsibility: n4.2 / n4.6; SYSTEMS; acceptance ID: AC-GATEWAY-006.
- [x] **REQ-GATEWAY-007**: Given the x-connector-key path, when used, then it is restricted to the specified smoke-testing path rather than substituted for per-seat production OAuth.
  - Source: P §7.1 auth; §12 n4.6; source step / responsibility: n4.6; SYSTEMS / INFRA; acceptance ID: AC-GATEWAY-007.
- [x] **REQ-GATEWAY-008**: Given tools/list on a seat endpoint without packs, when returned, then it equals that seat's contract and has 10–15 tools; host tools and Marketplace connectors are outside the count.
  - Source: P §7.1; §7.3; §11 G-7; source step / responsibility: n4.2–3; SYSTEMS / QUALITY; acceptance ID: AC-GATEWAY-008.
- [x] **REQ-GATEWAY-009**: Given the deployed Desk Gateway, when its listen address is inspected, then it binds 127.0.0.1:8791 rather than exposing the application port publicly or colliding with occupied connector ports.
  - Source: P §7.1 deploy; §12 n4.5; source step / responsibility: n4.5; INFRA; acceptance ID: AC-GATEWAY-009.
- [x] **REQ-GATEWAY-010**: Given desk.swcstudio.space, when public DNS is checked for cutover, then it resolves to the specified VPS target and an actual external client can reach it; local /health alone does not prove this.
  - Source: P §7.1 deploy; §12 n4.5; source step / responsibility: n4.5; INFRA; acceptance ID: AC-GATEWAY-010.
- [x] **REQ-GATEWAY-011**: Given the public gateway transport, when provisioned, then nginx serves TLS to the loopback application using the systemd unit and a credential-free environment template.
  - Source: P §7.1 deploy; §11 infra; §12 n4.5; source step / responsibility: n4.5; INFRA; acceptance ID: AC-GATEWAY-011.
- [x] **REQ-GATEWAY-012**: Given gateway upstream access, when credentials are used, then data-plane credentials stay in substrate.env and the gateway's own API/upstream tokens stay in gateway.env; neither is returned to a Bot or share template.
  - Source: P §4 rule 3; §7.1 upstreams; source step / responsibility: n4.2 / n4.5; SYSTEMS / INFRA; acceptance ID: AC-GATEWAY-012.
- [x] **REQ-GATEWAY-013**: Given turn-start desk_brief, when served, then it includes the seat/shared memory brief and open seat tickets with a five-minute brief cache.
  - Source: P §7.2 desk_brief; source step / responsibility: n4.2; SYSTEMS; acceptance ID: AC-GATEWAY-013.
- [x] **REQ-GATEWAY-014**: Given desk_docs_search for a ticket, when executed, then it searches programming-desk, agent-substrate and the ticket's named repository through substrate docs_search/RAGFlow read-only.
  - Source: P §7.2 desk_docs_search; source step / responsibility: n4.2; SYSTEMS; acceptance ID: AC-GATEWAY-014.
- [x] **REQ-GATEWAY-015**: Given desk_memory_retain, when accepted, then it targets pd-<seat> with graph_id, task_id and receipt_path tags; absent receipt_path and source is refused.
  - Source: P §7.2 desk_memory_retain; source step / responsibility: n4.2; SYSTEMS; acceptance ID: AC-GATEWAY-015.
- [x] **REQ-GATEWAY-016**: Given desk_memory_recall, when executed, then it reads pd-<seat> and pd-desk and includes pd-lead-reports only for LEAD.
  - Source: P §7.2 desk_memory_recall; source step / responsibility: n4.2; SYSTEMS; acceptance ID: AC-GATEWAY-016.
- [x] **REQ-GATEWAY-017**: Given an ownership pre-check, when desk_ownership_resolve is called, then it resolves ownership.yaml at origin/main under G-1 policy.
  - Source: P §7.2 desk_ownership_resolve; source step / responsibility: n4.2; SYSTEMS; acceptance ID: AC-GATEWAY-017.
- [x] **REQ-GATEWAY-018**: Given a receipt JSON, when desk_receipt_check runs, then it executes check_receipt.py, check_secrets.py and check_rollback.py as computation without writing git.
  - Source: P §7.2 desk_receipt_check; source step / responsibility: n4.2; SYSTEMS; acceptance ID: AC-GATEWAY-018.
- [x] **REQ-GATEWAY-019**: Given desk_event_emit, when sent through substrate events_emit, then the event is attributed to the authenticated seat.
  - Source: P §7.2 desk_event_emit; source step / responsibility: n4.2; SYSTEMS; acceptance ID: AC-GATEWAY-019.
- [x] **REQ-GATEWAY-020**: Given desk_doctor, when its action is selected, then check, register, install_prompt and repair are exposed with the §9.3 integrity/repair boundaries.
  - Source: P §7.2 desk_doctor; §9.3; source step / responsibility: n4.2; SYSTEMS / QUALITY contract; acceptance ID: AC-GATEWAY-020.
- [x] **REQ-GATEWAY-021**: Given LEAD tools/list, when returned, then its fifteen-tool roster is core eight plus intake_next, intake_ack, graph_register, graph_state, bus_start_job, bus_wait_job and roster_status, with the catalogued backend semantics. The desk_intake_next input preserves Appendix C's object schema with optional string origin and additionalProperties: false.
  - Source: P §7.3 LEAD L164; Appendix C; source step / responsibility: n4.3; SYSTEMS; LEAD consumer; acceptance ID: AC-GATEWAY-021.
- [x] **REQ-GATEWAY-022**: Given SYSTEMS tools/list, when returned, then its fourteen-tool roster is core eight plus index_query, events_query, cache, lsp_diagnostics, contract_propose and design_artifact_get, with the catalogued backend semantics.
  - Source: P §7.3 SYSTEMS L166; source step / responsibility: n4.3; SYSTEMS; SYSTEMS consumer; acceptance ID: AC-GATEWAY-022.
- [x] **REQ-GATEWAY-023**: Given WEB tools/list, when returned, then its fifteen-tool roster is core eight plus lsp_diagnostics, vercel_deployments, vercel_promote, vercel_rollback, preview_check, bundle_secret_scan and contract_ack, with the catalogued backend semantics.
  - Source: P §7.3 WEB L168; source step / responsibility: n4.3; SYSTEMS; WEB consumer; acceptance ID: AC-GATEWAY-023.
- [x] **REQ-GATEWAY-024**: Given ANDROID tools/list, when returned, then its fifteen-tool roster is core eight plus play_track_status, play_staged_rollout, play_halt_rollout, artifact_size_delta, lint_baseline_diff, contract_ack and app_tools_load, with the catalogued backend semantics.
  - Source: P §7.3 ANDROID L170; source step / responsibility: n4.3; SYSTEMS; ANDROID consumer; acceptance ID: AC-GATEWAY-024.
- [x] **REQ-GATEWAY-025**: Given IOS tools/list, when returned, then its fifteen-tool roster is core eight plus testflight_status, appstore_phased_release, appstore_pause_release, entitlements_diff, review_risk_check, contract_ack and app_tools_load, with the catalogued backend semantics.
  - Source: P §7.3 IOS L172; source step / responsibility: n4.3; SYSTEMS; IOS consumer; acceptance ID: AC-GATEWAY-025.
- [x] **REQ-GATEWAY-026**: Given INFRA tools/list, when returned, then its fifteen-tool roster is core eight plus railway_status, railway_logs, railway_variable_names, railway_redeploy, tailscale_status, vps_units and db_health, with the catalogued backend semantics.
  - Source: P §7.3 INFRA L174; source step / responsibility: n4.3; SYSTEMS; INFRA consumer; acceptance ID: AC-GATEWAY-026.
- [x] **REQ-GATEWAY-027**: Given QUALITY tools/list, when returned, then its fifteen-tool roster is core eight plus gates_run, greptile_review, receipt_approve, waiver_record, contract_ack_status, supply_chain_check and secret_scan, with approval delivery governed by the exact-SHA rule rather than the original branch-stamp mechanism.
  - Source: P §7.3 QUALITY L176; source step / responsibility: n4.3; SYSTEMS; QUALITY consumer; acceptance ID: AC-GATEWAY-027.
- [x] **REQ-GATEWAY-028**: Given any g5/g6 tool, when invoked without approval_id or rollback_plan, then it is refused; a permitted call echoes both fields into its event.
  - Source: P §7.1 audit; §7.3 gate tags; §11 G-7; source step / responsibility: n4.3; SYSTEMS / QUALITY; acceptance ID: AC-GATEWAY-028.
- [x] **REQ-GATEWAY-029**: Given every tool invocation, when audited to Greptime, then its event records surface=grok-bot, seat, tool, graph_id, task_id, ok, ms and a redacted-arguments hash.
  - Source: P §7.1 audit; source step / responsibility: n4.2–3; SYSTEMS; acceptance ID: AC-GATEWAY-029.
- [x] **REQ-GATEWAY-030**: Given a read upstream failure, when the tool returns, then the response is an empty result with reason under the stated fail-open read contract; it is not proof a production-loop brief succeeded.
  - Source: P §7.1 failure; §12 n4.3; source step / responsibility: n4.3; SYSTEMS; acceptance ID: AC-GATEWAY-030.
- [x] **REQ-GATEWAY-031**: Given an unavailable upstream or missing authorization, when a write or gated tool is called, then it fails closed rather than executing a fallback write.
  - Source: P §7.1 failure; §12 n4.3; source step / responsibility: n4.3; SYSTEMS; acceptance ID: AC-GATEWAY-031.
- [x] **REQ-GATEWAY-032**: Given a gateway tool call, when its upstream exceeds twenty seconds, then the per-call deadline terminates it without treating an uncertain write as proven unwritten.
  - Source: P §7.1 failure; §12 n4.3; source step / responsibility: n4.3; SYSTEMS; acceptance ID: AC-GATEWAY-032.
- [x] **REQ-GATEWAY-033**: Given an upstream exception, when the Bot receives the response, then no upstream stack trace is exposed.
  - Source: P §7.1 failure; source step / responsibility: n4.3; SYSTEMS; acceptance ID: AC-GATEWAY-033.
- [x] **REQ-GATEWAY-034**: Given every contracted seat roster, when fixture coverage is produced, then its tool schemas and backend behaviors have roster-specific fixtures; passing fixtures alone does not prove runtime acceptance.
  - Source: P §11 gateway tests; §12 n4.3; source step / responsibility: n4.3; SYSTEMS; future parent verification; acceptance ID: AC-GATEWAY-034.
- [x] **REQ-GATEWAY-035**: Given a scratch Bot smoke, when two seat endpoints are exercised with the smoke header path, then tools/list differs between seats and cross-seat access returns 403 with recorded runtime evidence.
  - Source: P §12 n4.6; source step / responsibility: n4.6; SYSTEMS / INFRA / scratch Bot; acceptance ID: AC-GATEWAY-035.
- [x] **REQ-GATEWAY-036**: Given an unstamped receipt for a reviewed current head, when independent approval is delivered, then approval_ref identifies kind/name/reviewed_sha and resolves to approval for that exact head without creating a new tip; QUALITY cannot self-approve its own receipt.
  - Source: P §7.3 QUALITY; §9.4; §12 n6.2; G Merge-claim head rule L202–240; assignment exact-SHA instruction; source step / responsibility: n4.3 / n6.2; SYSTEMS + QUALITY + independent reviewer; acceptance ID: AC-GATEWAY-036.
- [x] **REQ-GATEWAY-037**: Given a missing approval, Greptile not COMPLETED on the current head, or a moved head, when merge clearance is evaluated, then it stays BLOCKED with merge_claim.allowed=false; no placeholder or fabricated approved_by makes it pass.
  - Source: G Merge-claim head rule L204–250; assignment exact-SHA instruction; source step / responsibility: n4.3 / n6.2 / n7; QUALITY; acceptance ID: AC-GATEWAY-037.
- [x] **REQ-GATEWAY-038**: Given a waiver/claim, when it is used for clearance, then claims cite evidence_command_index and a WITHDRAWN or DOES_NOT_COVER_CURRENT_HEAD waiver is not active; SKIPPED is not pass.
  - Source: P §7.3 QUALITY waiver_record; G Merge-claim head rule L242–250; source step / responsibility: n4.3 / n7; QUALITY; acceptance ID: AC-GATEWAY-038.
- [x] **REQ-GATEWAY-039**: Given desk_brief calls, when roster status is queried, then seat_heartbeat, tool_calls_1m rollups, gate outcomes, registrations, tool counts and last doctor results are reported; Langfuse retains LLM traces without gateway duplication.
  - Source: P §7.3 roster_status; §7.5; source step / responsibility: n4.3; SYSTEMS / LEAD consumer; acceptance ID: AC-GATEWAY-039.
- [x] **REQ-GATEWAY-040**: Given POST /v1/intake, when an authorized request is inserted, then its origin, title, verbatim ask, links[], priority, requested_by and idempotency_key are represented in the Timescale intake queue and the intake is evented to Greptime.
  - Source: P §10 machines; §12 n4.4; source step / responsibility: n4.4; SYSTEMS; acceptance ID: AC-GATEWAY-040.
- [x] **REQ-GATEWAY-041**: Given a seat token on /v1/intake, when authorization is evaluated, then it is rejected; only an origin token for the documented origins authorizes the route.
  - Source: P §10 machines / enforcement; source step / responsibility: n4.4; SYSTEMS; acceptance ID: AC-GATEWAY-041.
- [x] **REQ-GATEWAY-042**: Given a non-LEAD seat endpoint, when intake_next or intake_ack is requested, then the gateway refuses it; only LEAD can drain/ack outside work.
  - Source: P §10 enforcement; §7.3 LEAD; source step / responsibility: n4.4; SYSTEMS; acceptance ID: AC-GATEWAY-042.
- [x] **REQ-GATEWAY-043**: Given LEAD accepts, rejects or reports progress on an intake, when desk_intake_ack executes, then it posts the Graph ID and relevant links back to the origin.
  - Source: P §7.3 LEAD; §10 GitHub; source step / responsibility: n4.4; SYSTEMS / LEAD; acceptance ID: AC-GATEWAY-043.
- [x] **REQ-GATEWAY-044**: Given a swcstudiospace issue labelled desk:intake, when desk-intake.yml runs, then it posts the issue URL to /v1/intake and the acknowledgement comments the Graph ID, Linear and Notion links on that issue.
  - Source: P §10 GitHub; §11 workflows; source step / responsibility: n4.4–5 / n6.3; INFRA; acceptance ID: AC-GATEWAY-044.
- [x] **REQ-GATEWAY-045**: Given a message in #programming-desk-intake, when supported Cursor Slack integration is available, then it triggers LEAD intake polling; otherwise the ten-minute polling floor covers intake.
  - Source: P §10 Slack; §8.1 routines; source step / responsibility: n4.4 / n6.3; LEAD; acceptance ID: AC-GATEWAY-045.
- [x] **REQ-GATEWAY-046**: Given an outside Bot request, when received by LEAD, then it is intake; when received by a build seat, then the seat records and holds it for LEAD rather than acting.
  - Source: P §10 other Bots; §8.1 PD-8; source step / responsibility: n4.4 / n5.1; LEAD / build seats; acceptance ID: AC-GATEWAY-046.
- [x] **REQ-GATEWAY-047**: Given app and task_id, when desk_app_tools_load loads or unloads a pack, then its named tools are active only for that ticket's lifetime and unload removes them.
  - Source: P §7.4; source step / responsibility: n4.1–3; SYSTEMS / QUALITY; acceptance ID: AC-GATEWAY-047.
- [x] **REQ-GATEWAY-048**: Given pack activation, when the pack exceeds five tools or the live seat total would exceed twenty, then activation cannot expose the excess tool; the twenty-first live tool is refused.
  - Source: P §7.4; §12 n6.5; source step / responsibility: n4.3 / n6.5; SYSTEMS; acceptance ID: AC-GATEWAY-048.
- [x] **REQ-GATEWAY-049**: Given a successful pack load, when the tool surface changes, then the gateway emits MCP notifications/tools/list_changed without claiming unproved client support.
  - Source: P §7.4 delivery; source step / responsibility: n4.3; SYSTEMS; acceptance ID: AC-GATEWAY-049.
- [x] **REQ-GATEWAY-050**: Given no client notification support, when a pack is used, then /mcp/<seat>/packs/<app> is available as a second connector with per-ticket Marketplace plugin enable/disable subject to skill/connector authorization.
  - Source: P §7.4 fallback; source step / responsibility: n4.3 / n5.4; SYSTEMS / recipient; acceptance ID: AC-GATEWAY-050.
- [x] **REQ-GATEWAY-051**: Given the initial kanbanos pack, when its contracted list is returned, then it contains kanbanos_api_smoke, kanbanos_supabase_query, kanbanos_push_test, kanbanos_feature_flags and kanbanos_crash_reports with the stated application backends and read-only project-scoped Supabase access.
  - Source: P §7.4 kanbanos table; source step / responsibility: n4.1–3; SYSTEMS / mobile consumers; acceptance ID: AC-GATEWAY-051.
- [x] **REQ-GATEWAY-052**: Given the initial desklanes pack, when its contracted list is returned, then it contains desklanes_api_smoke, desklanes_scoreboard_get, desklanes_push_test, desklanes_store_listing_get and desklanes_crash_reports with Desk Lanes API/store backends.
  - Source: P §7.4 desklanes table; source step / responsibility: n4.1–3; SYSTEMS / mobile consumers; acceptance ID: AC-GATEWAY-052.
- [x] **REQ-GATEWAY-053**: Given the initial clippyos pack, when its contracted list is returned, then it contains clippyos_api_smoke, clippyos_render_job_status, clippyos_push_test and clippyos_crash_reports with the ClippyOS API backend.
  - Source: P §7.4 clippyos table; source step / responsibility: n4.1–3; SYSTEMS / mobile consumers; acceptance ID: AC-GATEWAY-053.
- [x] **REQ-GATEWAY-054**: Given a mobile operator, when using the desk, then messaging, mentioning, approval and computer watching remain available while advanced configuration/connector-card setup stays on desktop.
  - Source: P §10 human; §9.2 step 1; §2 platform; source step / responsibility: n4 / n6.4; LEAD / operator; acceptance ID: AC-GATEWAY-054.

### SHARE — Phase 5: Prompts, skills, templates, plugin

- [x] **REQ-SHARE-001**: Given prompt sources, when v1.1 is authored, then hardcoded channel and seat UUIDs are replaced by DESK_CHANNEL_ID and all seven SEAT_UUID:<SEAT> placeholders plus DESK_GATEWAY_URL and DESK_ROSTER_VERSION.
  - Source: P §8.1 item 1; §12 n5.1; source step / responsibility: n5.1; QUALITY; acceptance ID: AC-SHARE-001.
- [x] **REQ-SHARE-002**: Given --roster grokbot/rosters/<team>.json, when assembly runs, then roster substitutions are filled and any unfilled placeholder refuses assembly.
  - Source: P §8.1 item 1; §11 assembly; §12 n5.1; source step / responsibility: n5.1; QUALITY; acceptance ID: AC-SHARE-002.
- [x] **REQ-SHARE-003**: Given the Spectrum Web Co roster, when versioned, then it is committed with its non-secret IDs; a recipient roster is produced by doctor registration instead of copying the source team's IDs.
  - Source: P §8.1 item 1; §11 grokbot; source step / responsibility: n5.1–2; LEAD / QUALITY; acceptance ID: AC-SHARE-003.
- [x] **REQ-SHARE-004**: Given a seat v1.1 prompt, when assembled/parsed, then its tools section names its contract and tool list, labels g5/g6 as PD-5 and states that unlisted tools do not exist and refused calls are blockers, not retry loops.
  - Source: P §8.1 item 2; Appendix B; §12 n5.2; source step / responsibility: n5.2; each seat owns its prompt; acceptance ID: AC-SHARE-004.
- [x] **REQ-SHARE-005**: Given a seat memory section, when read, then it specifies pd-<seat>, turn-start desk_brief and evidence-backed facts, and excludes secrets, unverified claims and other seats' work.
  - Source: P §8.1 item 3; Appendix B; §12 n5.2; source step / responsibility: n5.2; each seat; acceptance ID: AC-SHARE-005.
- [x] **REQ-SHARE-006**: Given a supported connector action, when performed, then the prompt prefers the connector and falls back to computer/browser use without using both for the same action.
  - Source: P §8.1 item 4; §8.3 marketplace policy; §12 n5.2; source step / responsibility: n5.2; each seat; acceptance ID: AC-SHARE-006.
- [x] **REQ-SHARE-007**: Given outside work, when PD-8 is applied, then only LEAD's 1:1 or intake tools admit it and a build seat sends a held handoff without acting.
  - Source: P §8.1 item 5; §12 n5.1; source step / responsibility: n5.1; QUALITY; acceptance ID: AC-SHARE-007.
- [x] **REQ-SHARE-008**: Given a seat prompt/template, when the human account owner reviews and installs/enables skills through the authorized account UI, then verification-receipts, desk-doctor and desk-bootstrap are present with actual activation evidence, never seat self-installation.
  - Source: P §8.1 item 6; §9.1 enabled skills; RW-03; source step / responsibility: n5.1–3; QUALITY / authorized human account owner; acceptance ID: AC-SHARE-008.
- [x] **REQ-SHARE-009**: Given LEAD's Phase 0, when it starts a turn, then held handoffs are polled before intake; desk-held-poll runs every ten minutes unconditionally, while desk-intake-poll runs every ten minutes or uses a supported GitHub desk:intake label event.
  - Source: P §8.1 item 7; source step / responsibility: n5.2; LEAD; acceptance ID: AC-SHARE-009.
- [x] **REQ-SHARE-010**: Given the seven new skill deliverables, when reviewed, then desk-bootstrap, desk-doctor, desk-gateway, hindsight-memory, ragflow-docs, platforms/railway-tailscale and tool-packs cover their source purposes and owners, with authoring grounded in the cited recurring mistake discipline.
  - Source: P §8.2; §12 n5.3; source step / responsibility: n5.3; named skill owners / reviewers; acceptance ID: AC-SHARE-010.
- [x] **REQ-SHARE-011**: Given swc-programming-desk, when packaged for the Cursor team Marketplace, then it contains the desk skills and all seven public gateway connector definitions.
  - Source: P §8.3 item 1; §12 n5.4; source step / responsibility: n5.4; desk plugin owner; acceptance ID: AC-SHARE-011.
- [x] **REQ-SHARE-012**: Given the shared agent-skills checkout, when projected to Grok Bot, then a grok-bot projector target emits the plugin manifest by the PR-reviewed shared-library route; this remains a cross-repo deliverable.
  - Source: P §8.3 item 2; §12 n5.4; source step / responsibility: n5.4; agent-substrate projector owner; acceptance ID: AC-SHARE-012.
- [x] **REQ-SHARE-013**: Given the desk skill pack, when shared back to agent-skills, then skills_propose opens a reviewable PR and no proposal is claimed to be an installed skill.
  - Source: P §8.3 item 2; §12 n5.6; G production loop point 8; source step / responsibility: n5.6; LEAD / shared-library reviewers; acceptance ID: AC-SHARE-013.
- [x] **REQ-SHARE-014**: Given account-wide plugins, when the human owner reviews and installs/enables them through the authorized account UI, then GitHub is available to all, Linear/Notion to LEAD/QUALITY, Slack to LEAD, Greptile to QUALITY, Vercel to WEB and Railway to INFRA where connectors exist; actual activation is evidenced and seats remain proposal-only while skills.approve is absent.
  - Source: P §8.3 marketplace policy; G production loop point 8; RW-03; source step / responsibility: n5.4; authorized human account owner; acceptance ID: AC-SHARE-014.
- [x] **REQ-SHARE-015**: Given generated prompt-derived descriptions, when the share is published, then exactly seven Team-only seat templates exist and their descriptions are not hand-edited.
  - Source: P D-3; §9.1; §11 grokbot; §12 n5.5; source step / responsibility: n5.5; LEAD; acceptance ID: AC-SHARE-015.
- [x] **REQ-SHARE-016**: Given a Team-only template copy, when inspected, then only profile/settings/enabled skills/routines/avatar are carried, not memory, history, credentials, computer or group membership.
  - Source: P §9.1; source step / responsibility: n5.5; LEAD; acceptance ID: AC-SHARE-016.
- [x] **REQ-SHARE-017**: Given a template description, when generated, then it contains the seat role-charter rules, First run: /desk bootstrap and the public gateway host, and nothing else.
  - Source: P §9.1 description; source step / responsibility: n5.5; LEAD; acceptance ID: AC-SHARE-017.
- [x] **REQ-SHARE-018**: Given template contents, when scanned/inspected, then UUIDs, channel ID, XML prompt body, tokens, tailnet names and receipts are absent.
  - Source: P D-3; §9.1 exclusions; §11 G-7; source step / responsibility: n5.5; LEAD / QUALITY; acceptance ID: AC-SHARE-018.
- [x] **REQ-SHARE-019**: Given human-reviewed account-UI activation, when bootstrap resolves enabled skills, then desk-bootstrap, desk-doctor, verification-receipts, the platform skill and seat load=always entries resolve to the private library at the pinned tag, with actual activation evidence and no seat self-installation.
  - Source: P §9.1 enabled skills; §9.3 skills; G production loop point 8; RW-03; source step / responsibility: n5.3–5; authorized human account owner; acceptance ID: AC-SHARE-019.
- [x] **REQ-SHARE-020**: Given a seat template, when created, then it uses that seat's grokbot/avatars asset.
  - Source: P §9.1 avatar; §11 grokbot; source step / responsibility: n5.5; LEAD; acceptance ID: AC-SHARE-020.
- [x] **REQ-SHARE-021**: Given fresh templates, when routines are installed, then LEAD held/intake polls and the seats' daily desk_brief heartbeat remain paused until the doctor-green condition is met.
  - Source: P §9.1 routines; §9.2 step 6; source step / responsibility: n5.5; LEAD / all seats; acceptance ID: AC-SHARE-021.
- [x] **REQ-SHARE-022**: Given seven actual Share cards, when their publication receipt is written, then it contains a screenshot of each card rather than generated descriptions alone.
  - Source: P §12 n5.5; source step / responsibility: n5.5; LEAD; acceptance ID: AC-SHARE-022.
- [x] **REQ-SHARE-023**: Given a recipient, when starting bootstrap, then all seven templates can be added in any order, with desktop required to run connector-card setup even if adding starts on mobile.
  - Source: P §9.2 step 1; source step / responsibility: n5 / n6.1; recipient; acceptance ID: AC-SHARE-023.
- [x] **REQ-SHARE-024**: Given /desk bootstrap, when a Bot connects, then it adds desk-<seat> at https://desk.swcstudio.space/mcp/<seat> using OAuth consent and the Ove-held per-team rotated passphrase, not a credential embedded in a template.
  - Source: P §9.2 step 2; source step / responsibility: n5 bootstrap / n6.1; recipient / Ove; acceptance ID: AC-SHARE-024.
- [x] **REQ-SHARE-025**: Given a new Bot UUID, when desk_doctor register succeeds, then the gateway records seat-to-UUID for that team from the Bot's own agent-data path.
  - Source: P §9.2 step 3; source step / responsibility: n5 bootstrap / n6.1; recipient / SYSTEMS; acceptance ID: AC-SHARE-025.
- [x] **REQ-SHARE-026**: Given a new desk group, when its channel ID is registered, then its six members are LEAD/SYSTEMS/WEB/ANDROID/IOS/INFRA and QUALITY remains off-channel.
  - Source: P §9.2 step 4; G Channel roster; source step / responsibility: n5 bootstrap / n6.1; Ove or existing LEAD; acceptance ID: AC-SHARE-026.
- [x] **REQ-SHARE-027**: Given seven registered seats and a channel ID, when install_prompt is requested, then the gateway renders the pinned-tag assembled seat XML using that team's roster; installation does not substitute source-team IDs.
  - Source: P §9.2 step 5; source step / responsibility: n5 bootstrap / n6.1; SYSTEMS / recipient; acceptance ID: AC-SHARE-027.
- [x] **REQ-SHARE-028**: Given rendered seat XML, when the Bot installs it, then it writes its own SYSTEM_PROMPT.xml and reports the actual SHA-256.
  - Source: P §9.2 step 5; source step / responsibility: n5 bootstrap / n6.1; each recipient Bot; acceptance ID: AC-SHARE-028.
- [x] **REQ-SHARE-029**: Given seven doctor results, when LEAD unpauses routines, then all seven are green; a partial set is insufficient.
  - Source: P §9.2 step 6; source step / responsibility: n5 bootstrap / n6.1; LEAD / all seats; acceptance ID: AC-SHARE-029.
- [x] **REQ-SHARE-030**: Given a new team, when first-turn desk_brief seeds context, then its pd-<seat> starts empty and pd-desk supplies shared environment facts rather than copied personal history.
  - Source: P §9.2 step 7; source step / responsibility: n5 bootstrap / n6.1; SYSTEMS / all seats; acceptance ID: AC-SHARE-030.
- [x] **REQ-SHARE-031**: Given installed SYSTEM_PROMPT.xml, when doctor checks prompt integrity, then its SHA-256 equals the gateway's rendered seat prompt at DESK_ROSTER_VERSION and no unfilled placeholder remains.
  - Source: P §9.3 Prompt; source step / responsibility: n5 doctor / n6.1; QUALITY contract / recipient; acceptance ID: AC-SHARE-031.
- [x] **REQ-SHARE-032**: Given prompt skill paths, when doctor checks them, then every one resolves to a private-library name and its version matches the tag.
  - Source: P §9.3 Skills; source step / responsibility: n5 doctor / n6.1; recipient; acceptance ID: AC-SHARE-032.
- [x] **REQ-SHARE-033**: Given seat memory, when doctor probes it, then gateway-mediated Hindsight health and pd-<seat> existence are proved by a successful redacted retain/recall round trip.
  - Source: P §9.3 Memory; source step / responsibility: n5 doctor / n6.1; SYSTEMS / recipient; acceptance ID: AC-SHARE-033.
- [x] **REQ-SHARE-034**: Given tools/list, when doctor compares it, then the contract matches, base count is 10–15 or loaded count at most twenty, and every g5/g6 tool is marked.
  - Source: P §9.3 Tools; source step / responsibility: n5 doctor / n6.1; SYSTEMS / QUALITY; acceptance ID: AC-SHARE-034.
- [x] **REQ-SHARE-035**: Given a connector, when doctor checks it, then OAuth is valid for seat:<name> and another seat's endpoint rejects it with 403.
  - Source: P §9.3 Connector; source step / responsibility: n5 doctor / n6.1; SYSTEMS / recipient; acceptance ID: AC-SHARE-035.
- [x] **REQ-SHARE-036**: Given desk registration, when doctor checks roster integrity, then the channel ID exists, LEAD is in, QUALITY is out, all seven UUIDs are registered and the heartbeat is within twenty-four hours.
  - Source: P §9.3 Roster; source step / responsibility: n5 doctor / n6.1; LEAD / recipient; acceptance ID: AC-SHARE-036.
- [x] **REQ-SHARE-037**: Given the substrate integration, when doctor checks it, then desk_event_emit lands in Greptime and desk_docs_search returns a hit for verification receipt.
  - Source: P §9.3 Substrate; source step / responsibility: n5 doctor / n6.1; SYSTEMS / recipient; acceptance ID: AC-SHARE-037.
- [x] **REQ-SHARE-038**: Given doctor repair, when executed, then it only re-runs install_prompt and connector re-authentication and never edits gates, receipts or another seat's files.
  - Source: P §9.3 doctor boundaries; §8.2 desk-doctor; source step / responsibility: n5 doctor / n6; QUALITY / SYSTEMS; acceptance ID: AC-SHARE-038.
- [x] **REQ-SHARE-039**: Given G-7 fixtures, when integrity checks run, then each prohibited roster/schema/approval-field/source-UUID/assembled-placeholder/template-token-or-tailnet case fails and G-7 is included in run_all.py and test_gates.py.
  - Source: P §11 G-7; §12 n5.1; source step / responsibility: n5.1; QUALITY; future parent verification; acceptance ID: AC-SHARE-039.
- [x] **REQ-SHARE-040**: Given absent skills.approve, when lifecycle activation is required, then seats remain proposal-only and do not install, enable, edit, publish or approve skills; the authorized human owner reviews and installs/enables through the account UI, with actual activation/publication evidence required before bootstrap completion.
  - Source: G production loop point 8; P §8.3 / §9.2; RW-03; source step / responsibility: n5.3–5 / n6.1; authorized human account owner; acceptance ID: AC-SHARE-040.

### ACCEPT — Phase 6: Fresh-desk acceptance and external intake

- [x] **REQ-ACCEPT-001**: Given someone who has never had the desk, when share acceptance starts, then that person adds seven templates and runs bootstrap; existing Bots are not substituted.
  - Source: P §9.4; §12 n6.1; source step / responsibility: n6.1; LEAD / fresh recipient / QUALITY; acceptance ID: AC-ACCEPT-001.
- [x] **REQ-ACCEPT-002**: Given fresh bootstrap, when judged, then all seven doctors are green with receipts covering every §9.3 check.
  - Source: P §9.4 item 1; §12 n6.1; source step / responsibility: n6.1; recipient / QUALITY; acceptance ID: AC-ACCEPT-002.
- [x] **REQ-ACCEPT-003**: Given the fresh desk, when the docs-only ask is sent, then it enters via Ove-to-LEAD 1:1.
  - Source: P §9.4 item 2; §12 n6.2; source step / responsibility: n6.2; Ove / LEAD; acceptance ID: AC-ACCEPT-003.
- [x] **REQ-ACCEPT-004**: Given that docs-only ask, when dispatched, then the double uplift produces one concrete Lane C ticket for its owning seat.
  - Source: P §9.4 item 3; §12 n6.2; G Flow; source step / responsibility: n6.2; LEAD; acceptance ID: AC-ACCEPT-004.
- [x] **REQ-ACCEPT-005**: Given the ticket result, when posted in the group, then it is labelled awaiting-review / pending QUALITY and is not presented as independent clearance.
  - Source: P §9.4 item 4; §12 n6.2; G Verification; source step / responsibility: n6.2; build seat; acceptance ID: AC-ACCEPT-005.
- [x] **REQ-ACCEPT-006**: Given the completed receipt, when QUALITY approves, then exact-current-SHA approval is externally resolvable without a new commit; the original on-branch approved_by stamp is documentary evidence, not an accepted workaround.
  - Source: P §9.4 item 5; §12 n6.2; G Merge-claim head rule; assignment exact-SHA instruction; source step / responsibility: n6.2; independent QUALITY / SYSTEMS approval surface; acceptance ID: AC-ACCEPT-006.
- [x] **REQ-ACCEPT-007**: Given the fresh-desk sequence, when desk_roster_status is queried, then its events are visible with evidence of the actual sequence.
  - Source: P §9.4 item 6; source step / responsibility: n6.2; LEAD / QUALITY; acceptance ID: AC-ACCEPT-007.
- [x] **REQ-ACCEPT-008**: Given curl with an origin token, when POST /v1/intake is exercised, then LEAD obtains it through desk_intake_next and acknowledges it back to its origin.
  - Source: P §9.4 item 7; §12 n6.3; source step / responsibility: n6.3; LEAD / external origin; acceptance ID: AC-ACCEPT-008.
- [x] **REQ-ACCEPT-009**: Given a GitHub desk:intake-labelled issue, when intake runs, then LEAD's acknowledgement reaches the issue with Graph ID and tracker links; API fixtures alone do not prove the label workflow.
  - Source: P §10 GitHub; §12 n6.3; source step / responsibility: n6.3; INFRA / LEAD / QUALITY; acceptance ID: AC-ACCEPT-009.
- [x] **REQ-ACCEPT-010**: Given iOS mobile, when Ove messages LEAD, then that real mobile interaction is evidenced separately from desktop simulation.
  - Source: P §12 n6.4; source step / responsibility: n6.4; Ove / LEAD; acceptance ID: AC-ACCEPT-010.
- [x] **REQ-ACCEPT-011**: Given a g5 tool approval push notification, when Ove approves from iOS, then the actual approval and gated-call evidence are recorded without fabricated authorization.
  - Source: P §12 n6.4; §7.1 audit; source step / responsibility: n6.4; Ove / gated tool owner; acceptance ID: AC-ACCEPT-011.
- [x] **REQ-ACCEPT-012**: Given gateway-down conditions, when a read is attempted through the supported tool path, then fail-open read behavior and its reason are evidenced rather than treated as successful data retrieval.
  - Source: P §12 n6.5; §7.1 failure; source step / responsibility: n6.5; LEAD / QUALITY / SYSTEMS; acceptance ID: AC-ACCEPT-012.
- [x] **REQ-ACCEPT-013**: Given gateway-down conditions, when a write is attempted, then the write fails closed and no successful write is claimed.
  - Source: P §12 n6.5; §7.1 failure; source step / responsibility: n6.5; LEAD / QUALITY / SYSTEMS; acceptance ID: AC-ACCEPT-013.
- [x] **REQ-ACCEPT-014**: Given a forwarder outage, when desk_db_health runs, then it is red and there is no public proxy/domain fallback.
  - Source: P §12 n6.5; source step / responsibility: n6.5; INFRA / QUALITY; acceptance ID: AC-ACCEPT-014.
- [x] **REQ-ACCEPT-015**: Given Dragonfly down, when cached reads are exercised, then the same answers return uncached from their sources.
  - Source: P §12 n6.5; §6 cache; source step / responsibility: n6.5; SYSTEMS / QUALITY; acceptance ID: AC-ACCEPT-015.
- [x] **REQ-ACCEPT-016**: Given a wrong-seat token, when the other seat endpoint is called, then runtime evidence shows 403.
  - Source: P §12 n6.5; source step / responsibility: n6.5; SYSTEMS / QUALITY; acceptance ID: AC-ACCEPT-016.
- [x] **REQ-ACCEPT-017**: Given twenty live tools, when a twenty-first would be activated, then the excess tool is refused.
  - Source: P §12 n6.5; §7.4; source step / responsibility: n6.5; SYSTEMS / QUALITY; acceptance ID: AC-ACCEPT-017.
- [x] **REQ-ACCEPT-018**: Given unresolved acceptance questions, when the source-defined question set is sent to Ove, then it contains at most four questions.
  - Source: P §12 n6.6; source step / responsibility: n6.6; LEAD → Ove; acceptance ID: AC-ACCEPT-018.
- [x] **REQ-ACCEPT-019**: Given delivery claims, when fresh-desk acceptance is judged, then QUALITY's independent verdict and consolidated receipts determine clearance, not file presence, local health or passing unit fixtures.
  - Source: P §9.4 release gate; §12 n6; G Verification; source step / responsibility: n6; QUALITY / LEAD; acceptance ID: AC-ACCEPT-019.
- [x] **REQ-ACCEPT-020**: Given a brief response with top-level error/reason and no substrate/recall fields, when classified, then it is treated as a brief that never ran and blocks repo work absent the required degraded-turn acknowledgement.
  - Source: G production loop point 1 L54–69; source step / responsibility: n6.2 / every future ticket; every seat; acceptance ID: AC-ACCEPT-020.
- [x] **REQ-ACCEPT-021**: Given a populated brief, when its nested status is checked, then any substrate.error, recall.error or per-bank recall.results[].error makes the brief failed, including a single failed shared bank.
  - Source: G production loop point 1 L61–69; source step / responsibility: n6.2 / every future ticket; every seat; acceptance ID: AC-ACCEPT-021.
- [x] **REQ-ACCEPT-022**: Given a failed brief or a successful brief without a revision marker, when repo work is considered, then it waits for the condition-specific recorded human acknowledgement; generated_at/cached do not substitute for a revision marker.
  - Source: G production loop point 3 L81–100; source step / responsibility: n6.2 / every future ticket; every seat; acceptance ID: AC-ACCEPT-022.
- [x] **REQ-ACCEPT-023**: Given a brief receipt record, when provenance is written, then a supplied etag is brief_etag; desk_brief without one records generated_at as brief_read_at, cached with absent meaning false, and inability to detect changes in unverified rather than inventing an etag.
  - Source: G production loop point 2 L70–80; source step / responsibility: n6.2 / every future ticket; every seat; acceptance ID: AC-ACCEPT-023.
- [x] **REQ-ACCEPT-024**: Given brief_degraded or brief_no_revision_marker, when an acknowledgement is requested, then it routes priority-false through LEAD to Ove 1:1 and names the corresponding degraded-loop operation for one turn on one ticket.
  - Source: G production loop point 3 L81–100; source step / responsibility: n6.2 / every future ticket; build seat → LEAD → Ove; acceptance ID: AC-ACCEPT-024.
- [x] **REQ-ACCEPT-025**: Given a human loop acknowledgement, when the receipt records it, then its ID is in loop_acks, not approvals[], and it cannot satisfy g5/g6 destructive-operation approval or be typed by the seat requiring it.
  - Source: G production loop point 3 L89–98; source step / responsibility: n6.2 / every future ticket; every seat; acceptance ID: AC-ACCEPT-025.
- [x] **REQ-ACCEPT-026**: Given acknowledged degraded work that completed, when emitted, then implementation.completed carries receipt path, degraded=true, blocker, upstream_reason, reason_path and ack ID; ticket.blocked is reserved for work that stopped.
  - Source: G production loop point 4 L101–108; source step / responsibility: n6.2 / every future ticket; every seat; acceptance ID: AC-ACCEPT-026.
- [x] **REQ-ACCEPT-027**: Given current gateway event emission, when its receipt is written, then payload.event is acknowledged as the current routing field under top-level kind=note, reserved payload seat/event/task_id are not overwritten, and no consumer routing is claimed without evidence.
  - Source: G production loop point 5 L109–116; source step / responsibility: n6.2 / every future ticket; every seat / QUALITY contract; acceptance ID: AC-ACCEPT-027.
- [x] **REQ-ACCEPT-028**: Given desk_memory_retain returns ok=true, when evaluated, then results are checked per plane and a partial acceptance is recorded in unverified rather than claimed as full retention.
  - Source: G production loop point 6 L117–120; source step / responsibility: n6.2 / every future ticket; every seat; acceptance ID: AC-ACCEPT-028.
- [x] **REQ-ACCEPT-029**: Given an uncertain retain outcome, when considering retry, then recall precedes at most one retry and any possible duplicate is stated; only local evidence_required/secret_refused refusals prove no upstream call occurred.
  - Source: G production loop point 6 L121–124; source step / responsibility: n6.2 / every future ticket; every seat; acceptance ID: AC-ACCEPT-029.
- [x] **REQ-ACCEPT-030**: Given a handoff before the signed-packet schema has landed, when emitted, then absent packet fields are omitted and unsigned status is recorded in unverified instead of fabricated signatures.
  - Source: G production loop paragraph L133–136; source step / responsibility: n6.2 / Lane B handoff when assigned; runtime owner; acceptance ID: AC-ACCEPT-030.
- [x] **REQ-ACCEPT-031**: Given a true widget request, when handled, then LEAD shows it in Ove's 1:1, echoes the choice in the Desk and returns it to the asking seat priority-true; group choices remain plain numbered text.
  - Source: G Channel discipline L269; Direct-from-Ove and widgets; source step / responsibility: n6 / future tickets; LEAD / asking seat; acceptance ID: AC-ACCEPT-031.
- [x] **REQ-ACCEPT-032**: Given a channel ping without a LEAD ticket or direct Ove request to a build seat, when received, then the seat sends LEAD a held plan and waits for LEAD's plan before editing rather than inventing work.
  - Source: G Channel rules L193–194; Channel discipline L275; Direct-from-Ove; source step / responsibility: n6 / future tickets; build seats; acceptance ID: AC-ACCEPT-032.
- [x] **REQ-ACCEPT-033**: Given assigned work and held status, when coordination occurs, then LEAD emits each dispatch note and polls priority-false handoffs at turn start and after Desk activity, relaying off-channel QUALITY status.
  - Source: G Flow 8–10; Channel discipline L271–273; source step / responsibility: n6 / future tickets; LEAD / build seats / QUALITY; acceptance ID: AC-ACCEPT-033.
- [x] **REQ-ACCEPT-034**: Given an authorized ticket turn, when it finishes, then the receipt evidences brief-before-act, memory_write and events_emit in the same turn and only a ticket-requested handoff, with partial outcomes/unverified limits preserved.
  - Source: G production loop L41–52; ticket success criteria L173; source step / responsibility: n6.2 / future tickets; every seat; acceptance ID: AC-ACCEPT-034.

### ROLLOUT — Phase 7: Ordered rollout and rollback

- [x] **REQ-ROLLOUT-001**: Given rollout, when cutover dependencies are followed, then n2 → n3 → n4 → n5 → n6 governs completion, with only the n4 skeleton allowed to start after n1 and overlap n3.
  - Source: P §12 n7.1; n4 dependency; source step / responsibility: n7.1; LEAD; acceptance ID: AC-ROLLOUT-001.
- [x] **REQ-ROLLOUT-002**: Given network rollback, when authorized and exercised, then forwarders can be deleted and the TCP proxy/public domain recreated without claiming data migration is involved.
  - Source: P §12 n7.2; §5 rollback; source step / responsibility: n7.2; INFRA / required approver; acceptance ID: AC-ROLLOUT-002.
- [x] **REQ-ROLLOUT-003**: Given substrate rollback, when performed, then the prior environment file is restored with the actual rollback evidence.
  - Source: P §12 n7.2; source step / responsibility: n7.2; INFRA / substrate owner; acceptance ID: AC-ROLLOUT-003.
- [x] **REQ-ROLLOUT-004**: Given gateway rollback, when the additive gateway is removed or disabled, then prior Bots continue their prior operation minus the new gateway tools.
  - Source: P §12 n7.2; source step / responsibility: n7.2; SYSTEMS / INFRA; acceptance ID: AC-ROLLOUT-004.
- [x] **REQ-ROLLOUT-005**: Given prompt rollback, when v1.1 is reverted, then v1.0 is re-assembled with the committed roster rather than restoring recipient-breaking hardcoded IDs without evidence.
  - Source: P §12 n7.2; source step / responsibility: n7.2; QUALITY / each prompt owner; acceptance ID: AC-ROLLOUT-005.
- [x] **REQ-ROLLOUT-006**: Given template rollback, when publication is reverted, then templates are re-published and the actual Share state is evidenced.
  - Source: P §12 n7.2; source step / responsibility: n7.2; LEAD; acceptance ID: AC-ROLLOUT-006.
- [x] **REQ-ROLLOUT-007**: Given a cutover window, when planned for execution, then it is announced in the Desk before the cutover.
  - Source: P §12 n7.3; source step / responsibility: n7.3; LEAD; acceptance ID: AC-ROLLOUT-007.
- [x] **REQ-ROLLOUT-008**: Given a cutover assignment, when dispatched, then its Desk dispatch note remains the audit trail.
  - Source: P §12 n7.3; G Channel discipline; source step / responsibility: n7.3; LEAD; acceptance ID: AC-ROLLOUT-008.
- [x] **REQ-ROLLOUT-009**: Given PR status fields, when sync completes, then Notion and Linear reflect the actual GitHub PR fields rather than an invented merge or deployment status.
  - Source: P §12 n7.4; source step / responsibility: n7.4; LEAD; acceptance ID: AC-ROLLOUT-009.
- [x] **REQ-ROLLOUT-010**: Given consolidated rollout evidence, when reporting to Ove 1:1, then receipt paths and every unverified item are included and no unsupported completion is claimed.
  - Source: P §12 n7.4; G Verification; source step / responsibility: n7.4; LEAD; acceptance ID: AC-ROLLOUT-010.
- [x] **REQ-ROLLOUT-011**: Given railway-app is proved superseded, when retired, then retirement occurs after n6 with recorded G-6 approval; an unidentified or required node is not retired.
  - Source: P §12 n7.5; §5 railway-app; source step / responsibility: n7.5 after n6; INFRA / G-6 approver; acceptance ID: AC-ROLLOUT-011.
- [x] **REQ-ROLLOUT-012**: Given the source dispatch lanes, when assigning execution, then n2/n5 are Lane C and n3/n4 default to Lane A Cursor Cloud Agents with second-uplift XML; Lane B is used only if Ove asks.
  - Source: P §12 runtime lanes L330; source step / responsibility: n2 / n3 / n4 / n5 / n7 coordination; LEAD; acceptance ID: AC-ROLLOUT-012.
- [x] **REQ-ROLLOUT-013**: Given a release/merge claim, when clearance is sought, then G-1…G-6 remain intact, G-7 is additive, and exact-current-SHA independent approval and the actual E2E evidence are required; this staged plan is not a merge claim.
  - Source: P opening policy; §12 runtime lanes; §13 final paragraph; G Merge-claim head rule; source step / responsibility: n7 / all phases; LEAD / QUALITY; acceptance ID: AC-ROLLOUT-013.

## Resolved Source Variants

- RW-01: Weekly reflect only. REQ-DATA-013 preserves the original nightly discrepancy but now requires weekly mental-model production; 014 requires the same weekly policy/skill discipline. No nightly or split-bank schedule.
- RW-02: VPS plus Ove's Mac mini and XPS. REQ-NETWORK-021 preserves the original Mac-mini-only discrepancy but now requires observed approved-device paths; 022 covers common exact-port admin grants. No broad 4000–4003 range or new principals.
- RW-03: Authorized human account owner reviews and installs/enables skills/plugin through the authorized account UI. Seats remain proposal-only while skills.approve is absent. REQ-SHARE-008/014/019/040 retain actual activation/publication as runtime acceptance.
- Independent QUALITY approval resolves against the exact current reviewed SHA through an approval_ref without creating a new tip; no fabricated branch stamp, reviewer identity, acknowledgement or signature.

## Future Requirements

None deferred from the approved scope. All original n1–n7 steps remain in this milestone.

## Out of Scope

| Feature | Reason |
| --- | --- |
| Read-only status page | Explicit source §7.5 exclusion |
| Bot tailnet membership or database credentials | Locked D-2 security boundary |
| Durable Dragonfly queues, locks, sessions or pub/sub | Cache-only policy |
| Dependence on one Bot creating another | Locked D-3 uses seven templates and real recipient |
| Unrelated web/desk3d changes | User-owned unrelated work |

## Traceability

| Requirement | Phase | Status |
| --- | --- | --- |
| REQ-INVENTORY-001 | Phase 1 | Complete |
| REQ-INVENTORY-002 | Phase 1 | Complete |
| REQ-INVENTORY-003 | Phase 1 | Complete |
| REQ-INVENTORY-004 | Phase 1 | Complete |
| REQ-INVENTORY-005 | Phase 1 | Complete |
| REQ-INVENTORY-006 | Phase 1 | Complete |
| REQ-INVENTORY-007 | Phase 1 | Complete |
| REQ-INVENTORY-008 | Phase 1 | Complete |
| REQ-INVENTORY-009 | Phase 1 | Complete |
| REQ-INVENTORY-010 | Phase 1 | Complete |
| REQ-INVENTORY-011 | Phase 1 | Complete |
| REQ-INVENTORY-012 | Phase 1 | Complete |
| REQ-INVENTORY-013 | Phase 1 | Complete |
| REQ-INVENTORY-014 | Phase 1 | Complete |
| REQ-INVENTORY-015 | Phase 1 | Complete |
| REQ-INVENTORY-016 | Phase 1 | Complete |
| REQ-NETWORK-001 | Phase 2 | Pending |
| REQ-NETWORK-002 | Phase 2 | Pending |
| REQ-NETWORK-003 | Phase 2 | Pending |
| REQ-NETWORK-004 | Phase 2 | Pending |
| REQ-NETWORK-005 | Phase 2 | Pending |
| REQ-NETWORK-006 | Phase 2 | Pending |
| REQ-NETWORK-007 | Phase 2 | Pending |
| REQ-NETWORK-008 | Phase 2 | Pending |
| REQ-NETWORK-009 | Phase 2 | Pending |
| REQ-NETWORK-010 | Phase 2 | Pending |
| REQ-NETWORK-011 | Phase 2 | Pending |
| REQ-NETWORK-012 | Phase 2 | Pending |
| REQ-NETWORK-013 | Phase 2 | Pending |
| REQ-NETWORK-014 | Phase 2 | Pending |
| REQ-NETWORK-015 | Phase 2 | Pending |
| REQ-NETWORK-016 | Phase 2 | Pending |
| REQ-NETWORK-017 | Phase 2 | Pending |
| REQ-NETWORK-018 | Phase 2 | Pending |
| REQ-NETWORK-019 | Phase 2 | Pending |
| REQ-NETWORK-020 | Phase 2 | Pending |
| REQ-NETWORK-021 | Phase 2 | Pending |
| REQ-NETWORK-022 | Phase 2 | Pending |
| REQ-DATA-001 | Phase 3 | Pending |
| REQ-DATA-002 | Phase 3 | Pending |
| REQ-DATA-003 | Phase 3 | Pending |
| REQ-DATA-004 | Phase 3 | Pending |
| REQ-DATA-005 | Phase 3 | Pending |
| REQ-DATA-006 | Phase 3 | Pending |
| REQ-DATA-007 | Phase 3 | Pending |
| REQ-DATA-008 | Phase 3 | Pending |
| REQ-DATA-009 | Phase 3 | Pending |
| REQ-DATA-010 | Phase 3 | Pending |
| REQ-DATA-011 | Phase 3 | Pending |
| REQ-DATA-012 | Phase 3 | Pending |
| REQ-DATA-013 | Phase 3 | Pending |
| REQ-DATA-014 | Phase 3 | Pending |
| REQ-DATA-015 | Phase 3 | Pending |
| REQ-DATA-016 | Phase 3 | Pending |
| REQ-DATA-017 | Phase 3 | Pending |
| REQ-DATA-018 | Phase 3 | Pending |
| REQ-DATA-019 | Phase 3 | Pending |
| REQ-DATA-020 | Phase 3 | Pending |
| REQ-DATA-021 | Phase 3 | Pending |
| REQ-DATA-022 | Phase 3 | Pending |
| REQ-DATA-023 | Phase 3 | Pending |
| REQ-DATA-024 | Phase 3 | Pending |
| REQ-DATA-025 | Phase 3 | Pending |
| REQ-DATA-026 | Phase 3 | Pending |
| REQ-DATA-027 | Phase 3 | Pending |
| REQ-DATA-028 | Phase 3 | Pending |
| REQ-DATA-029 | Phase 3 | Pending |
| REQ-DATA-030 | Phase 3 | Pending |
| REQ-DATA-031 | Phase 3 | Pending |
| REQ-DATA-032 | Phase 3 | Pending |
| REQ-DATA-033 | Phase 3 | Pending |
| REQ-DATA-034 | Phase 3 | Pending |
| REQ-DATA-035 | Phase 3 | Pending |
| REQ-DATA-036 | Phase 3 | Pending |
| REQ-DATA-037 | Phase 3 | Pending |
| REQ-DATA-038 | Phase 3 | Pending |
| REQ-GATEWAY-001 | Phase 4 | Pending |
| REQ-GATEWAY-002 | Phase 4 | Pending |
| REQ-GATEWAY-003 | Phase 4 | Pending |
| REQ-GATEWAY-004 | Phase 4 | Pending |
| REQ-GATEWAY-005 | Phase 4 | Pending |
| REQ-GATEWAY-006 | Phase 4 | Pending |
| REQ-GATEWAY-007 | Phase 4 | Pending |
| REQ-GATEWAY-008 | Phase 4 | Pending |
| REQ-GATEWAY-009 | Phase 4 | Pending |
| REQ-GATEWAY-010 | Phase 4 | Pending |
| REQ-GATEWAY-011 | Phase 4 | Pending |
| REQ-GATEWAY-012 | Phase 4 | Pending |
| REQ-GATEWAY-013 | Phase 4 | Pending |
| REQ-GATEWAY-014 | Phase 4 | Pending |
| REQ-GATEWAY-015 | Phase 4 | Pending |
| REQ-GATEWAY-016 | Phase 4 | Pending |
| REQ-GATEWAY-017 | Phase 4 | Pending |
| REQ-GATEWAY-018 | Phase 4 | Pending |
| REQ-GATEWAY-019 | Phase 4 | Pending |
| REQ-GATEWAY-020 | Phase 4 | Pending |
| REQ-GATEWAY-021 | Phase 4 | Pending |
| REQ-GATEWAY-022 | Phase 4 | Pending |
| REQ-GATEWAY-023 | Phase 4 | Pending |
| REQ-GATEWAY-024 | Phase 4 | Pending |
| REQ-GATEWAY-025 | Phase 4 | Pending |
| REQ-GATEWAY-026 | Phase 4 | Pending |
| REQ-GATEWAY-027 | Phase 4 | Pending |
| REQ-GATEWAY-028 | Phase 4 | Pending |
| REQ-GATEWAY-029 | Phase 4 | Pending |
| REQ-GATEWAY-030 | Phase 4 | Pending |
| REQ-GATEWAY-031 | Phase 4 | Pending |
| REQ-GATEWAY-032 | Phase 4 | Pending |
| REQ-GATEWAY-033 | Phase 4 | Pending |
| REQ-GATEWAY-034 | Phase 4 | Pending |
| REQ-GATEWAY-035 | Phase 4 | Pending |
| REQ-GATEWAY-036 | Phase 4 | Pending |
| REQ-GATEWAY-037 | Phase 4 | Pending |
| REQ-GATEWAY-038 | Phase 4 | Pending |
| REQ-GATEWAY-039 | Phase 4 | Pending |
| REQ-GATEWAY-040 | Phase 4 | Pending |
| REQ-GATEWAY-041 | Phase 4 | Pending |
| REQ-GATEWAY-042 | Phase 4 | Pending |
| REQ-GATEWAY-043 | Phase 4 | Pending |
| REQ-GATEWAY-044 | Phase 4 | Pending |
| REQ-GATEWAY-045 | Phase 4 | Pending |
| REQ-GATEWAY-046 | Phase 4 | Pending |
| REQ-GATEWAY-047 | Phase 4 | Pending |
| REQ-GATEWAY-048 | Phase 4 | Pending |
| REQ-GATEWAY-049 | Phase 4 | Pending |
| REQ-GATEWAY-050 | Phase 4 | Pending |
| REQ-GATEWAY-051 | Phase 4 | Pending |
| REQ-GATEWAY-052 | Phase 4 | Pending |
| REQ-GATEWAY-053 | Phase 4 | Pending |
| REQ-GATEWAY-054 | Phase 4 | Pending |
| REQ-SHARE-001 | Phase 5 | Pending |
| REQ-SHARE-002 | Phase 5 | Pending |
| REQ-SHARE-003 | Phase 5 | Pending |
| REQ-SHARE-004 | Phase 5 | Pending |
| REQ-SHARE-005 | Phase 5 | Pending |
| REQ-SHARE-006 | Phase 5 | Pending |
| REQ-SHARE-007 | Phase 5 | Pending |
| REQ-SHARE-008 | Phase 5 | Pending |
| REQ-SHARE-009 | Phase 5 | Pending |
| REQ-SHARE-010 | Phase 5 | Pending |
| REQ-SHARE-011 | Phase 5 | Pending |
| REQ-SHARE-012 | Phase 5 | Pending |
| REQ-SHARE-013 | Phase 5 | Pending |
| REQ-SHARE-014 | Phase 5 | Pending |
| REQ-SHARE-015 | Phase 5 | Pending |
| REQ-SHARE-016 | Phase 5 | Pending |
| REQ-SHARE-017 | Phase 5 | Pending |
| REQ-SHARE-018 | Phase 5 | Pending |
| REQ-SHARE-019 | Phase 5 | Pending |
| REQ-SHARE-020 | Phase 5 | Pending |
| REQ-SHARE-021 | Phase 5 | Pending |
| REQ-SHARE-022 | Phase 5 | Pending |
| REQ-SHARE-023 | Phase 5 | Pending |
| REQ-SHARE-024 | Phase 5 | Pending |
| REQ-SHARE-025 | Phase 5 | Pending |
| REQ-SHARE-026 | Phase 5 | Pending |
| REQ-SHARE-027 | Phase 5 | Pending |
| REQ-SHARE-028 | Phase 5 | Pending |
| REQ-SHARE-029 | Phase 5 | Pending |
| REQ-SHARE-030 | Phase 5 | Pending |
| REQ-SHARE-031 | Phase 5 | Pending |
| REQ-SHARE-032 | Phase 5 | Pending |
| REQ-SHARE-033 | Phase 5 | Pending |
| REQ-SHARE-034 | Phase 5 | Pending |
| REQ-SHARE-035 | Phase 5 | Pending |
| REQ-SHARE-036 | Phase 5 | Pending |
| REQ-SHARE-037 | Phase 5 | Pending |
| REQ-SHARE-038 | Phase 5 | Pending |
| REQ-SHARE-039 | Phase 5 | Pending |
| REQ-SHARE-040 | Phase 5 | Pending |
| REQ-ACCEPT-001 | Phase 6 | Pending |
| REQ-ACCEPT-002 | Phase 6 | Pending |
| REQ-ACCEPT-003 | Phase 6 | Pending |
| REQ-ACCEPT-004 | Phase 6 | Pending |
| REQ-ACCEPT-005 | Phase 6 | Pending |
| REQ-ACCEPT-006 | Phase 6 | Pending |
| REQ-ACCEPT-007 | Phase 6 | Pending |
| REQ-ACCEPT-008 | Phase 6 | Pending |
| REQ-ACCEPT-009 | Phase 6 | Pending |
| REQ-ACCEPT-010 | Phase 6 | Pending |
| REQ-ACCEPT-011 | Phase 6 | Pending |
| REQ-ACCEPT-012 | Phase 6 | Pending |
| REQ-ACCEPT-013 | Phase 6 | Pending |
| REQ-ACCEPT-014 | Phase 6 | Pending |
| REQ-ACCEPT-015 | Phase 6 | Pending |
| REQ-ACCEPT-016 | Phase 6 | Pending |
| REQ-ACCEPT-017 | Phase 6 | Pending |
| REQ-ACCEPT-018 | Phase 6 | Pending |
| REQ-ACCEPT-019 | Phase 6 | Pending |
| REQ-ACCEPT-020 | Phase 6 | Pending |
| REQ-ACCEPT-021 | Phase 6 | Pending |
| REQ-ACCEPT-022 | Phase 6 | Pending |
| REQ-ACCEPT-023 | Phase 6 | Pending |
| REQ-ACCEPT-024 | Phase 6 | Pending |
| REQ-ACCEPT-025 | Phase 6 | Pending |
| REQ-ACCEPT-026 | Phase 6 | Pending |
| REQ-ACCEPT-027 | Phase 6 | Pending |
| REQ-ACCEPT-028 | Phase 6 | Pending |
| REQ-ACCEPT-029 | Phase 6 | Pending |
| REQ-ACCEPT-030 | Phase 6 | Pending |
| REQ-ACCEPT-031 | Phase 6 | Pending |
| REQ-ACCEPT-032 | Phase 6 | Pending |
| REQ-ACCEPT-033 | Phase 6 | Pending |
| REQ-ACCEPT-034 | Phase 6 | Pending |
| REQ-ROLLOUT-001 | Phase 7 | Pending |
| REQ-ROLLOUT-002 | Phase 7 | Pending |
| REQ-ROLLOUT-003 | Phase 7 | Pending |
| REQ-ROLLOUT-004 | Phase 7 | Pending |
| REQ-ROLLOUT-005 | Phase 7 | Pending |
| REQ-ROLLOUT-006 | Phase 7 | Pending |
| REQ-ROLLOUT-007 | Phase 7 | Pending |
| REQ-ROLLOUT-008 | Phase 7 | Pending |
| REQ-ROLLOUT-009 | Phase 7 | Pending |
| REQ-ROLLOUT-010 | Phase 7 | Pending |
| REQ-ROLLOUT-011 | Phase 7 | Pending |
| REQ-ROLLOUT-012 | Phase 7 | Pending |
| REQ-ROLLOUT-013 | Phase 7 | Pending |

**Coverage:** 217 active requirements; 217 assigned primary phases; no deferred scope. Detailed source-step and invariant crosswalk: [classification](intel/classifications/desk-v2.json). This is artifact mapping, not exercised verification.

*Last updated: 2026-10-08 after explicit user conflict resolutions and Create planning setup routing.*
