# Desk v2 — Staged Source Constraints

- task_id: SynthesizeDeskV2Intel
- correlation_id: desk-v2-autonomous-2026-10-08
- status: STAGED_NOT_VALIDATED; source contracts, not implementation design or exercised verification
- source aliases: [P — docs/upgrade-plan-desk-v2.md](../../docs/upgrade-plan-desk-v2.md); [G — docs/desk-operating-model.md](../../docs/desk-operating-model.md)

These constraints extract the approved source's specified mechanisms and current governance. They do not introduce new libraries/APIs, expand product scope, schedule work or declare deployment. REQ-* coverage is in requirements.md. All catalogue names below include the full desk_ prefix; every table row describes the observable contract of that specific tool, including limitations the source states. Source test commands are future parent evidence requirements, never commands executed here.

## C-01: Locked topology and external addressing

- source: P §3 D-1/D-2/D-3; §4 rules 1–4; G Channel roster
- type: protocol
- content: Seven seats; group members are LEAD, SYSTEMS, WEB, ANDROID, IOS, INFRA (platform maximum six); QUALITY is off-channel. Outside humans/machines/other desks reach LEAD 1:1 or the LEAD-only intake queue. Bots use the public VPS gateway. Railway has one private-network forwarder per project/environment. GitHub remains shipment truth; data planes are ledger/index/cache/memory/retrieval, not substitutes for shipped-work truth.

## C-02: Network address and mapping evidence

- source: P §5 mechanism/mapping table/VPS cutover, L95–106; §13 service names
- type: schema
- content: Service names/ports are provisional until n1 confirms them. Ultrathink/production forwarder expected name ultrathink-production-tailscale-forwarder maps 4000→greptimedb.railway.internal:4000 (HTTP SQL), 4001→:4001 (gRPC), 4003→:4003 (Postgres wire), 5432→timescaledb.railway.internal:5432 and 6379→dragonfly.railway.internal:6379. Agent Substrate/production expected name agent-substrate-production-tailscale-forwarder maps 8888→hindsight-api.railway.internal:8888 (REST and /mcp/<bank>/), 9380→ragflow.railway.internal:9380 (API) and optionally 80→ragflow.railway.internal:80 (web). Railway private networking is per project and environment (fd12::/16 and *.railway.internal), not inter-project reachability. Forwarder identity persists on a volume. GREPTIME_URL, SUBSTRATE_PG_URL, DRAGONFLY_URL, HINDSIGHT_URL and RAGFLOW_URL use these MagicDNS names after cutover; no secret URL value is copied into this artifact. Parent observation of additional listener ports 4002/9382 does not silently expand the five specified mappings or ACL.

## C-03: Tailnet least-privilege and exposure

- source: P §5 ACL/retire public exposure/Bot computers; §12 n2.3/n2.5/n7.5
- type: nfr
- content: tag:railway-forwarder identifies both forwarders; tag:vps identifies the VPS; tag:admin identifies administrative devices, with Ove's Mac mini and XPS selected by the user in RW-02. Only the VPS and those two admin devices reach exact mapped ports; all else denied. Original Mac-mini-only wording remains discrepancy provenance, not an active alternative. Forwarder key expiry disabled, reusable tagged auth key, ephemeral off. WireGuard protects plaintext service-port traffic; Hindsight and RAGFlow still require bearer keys. Public Timescale TCP proxy and Greptime domain retire only after verified cutover with G-6 approval and recreation rollback. hindsight-ui public access remains Ove's explicit optional choice behind its access key. railway-app can be adopted if actually a suitable forwarder; if superseded it retires only after n6 under G-6. Bot normal egress is HTTPS; allowlist the gateway when required. Mac-mini egress routing is an INFRA-only emergency dependency, not the default Bot network.

## C-04: Credential partition and redaction

- source: P §4 rule 3; §5 VPS cutover; §6 forbidden data; §7.1 upstreams/audit; §9.1; G production loop point 7
- type: nfr
- content: Greptime, Timescale, Dragonfly, Hindsight and RAGFlow credentials stay in /etc/substrate/substrate.env and are used by substrate-mcp. Gateway holds only its own upstream API tokens in /etc/desk-gateway/gateway.env for Railway, Vercel, Play, App Store Connect, Greptile and agent bus. A Bot/template never receives either category. Gateway contacts the substrate/data planes through the specified boundary; no seat defaults to raw Hindsight/RAGFlow MCP/HTTP. D-04 redactor runs before forbidden secret payload retention/ledger emission. RAGFlow excludes receipts/transcripts as well as secrets. Environment templates have names but no values.

## C-05: Data classes, ownership and retention

- source: P §6 table L122–128; §12 n3; §13 Hindsight version/model
- type: schema
- content:
  - Greptime agent_events: every tool call, receipt, dispatch, intake and heartbeat; gateway events_emit and substrate collectors write; append-only hash/prev chain; hourly Merkle root anchored by packages/ledger to Solana devnet; 180 hot days then export; no secrets/full transcripts.
  - Timescale: graph_index/graph_nodes/graph_steps plus desk_intake, desk_claims, desk_idempotency, desk_receipts, seat_roster, tool_pack_state; substrate/gateway writers. Intake drains with FOR UPDATE SKIP LOCKED. Claims have per-Graph-ID expiry. Processed-key record is thirty days. Rows remain open-Graph lifetime plus ninety days, aggregates one year. seat_heartbeat/tool_calls_1m are hypertables with continuous aggregates. GitHub/Linear/Notion rebuild indexes except the small intake queue; none becomes shipment truth.
  - Dragonfly: cache only; brief five minutes, docs_search/recall ten minutes, counters one hour, key mirror twenty-four hours. No sessions, durable queue, pub/sub, locks or irreplaceable records. Reads fall through on loss.
  - Hindsight: pd-desk shared (LEAD/QUALITY write, all read), pd-<seat> owner writes, pd-lead-reports for LEAD recall. Substrate tenant-key holder alone routes retain/recall; verified receipt path/source URL required. Retain forever. Weekly reflect/pruning into mental models is user-selected RW-01; no nightly or split-bank schedule. Original nightly wording remains discrepancy provenance. Replaces Agentmemory/local Claude hindsight; Hermes provider none with backup. Actual /health version/embedding dimensions are prerequisites, not inferred from template v0.10.1-slim.
  - RAGFlow: programming-desk, agent-substrate and each product repo dataset (including KanbanOS, Desk Lanes, ClippyOS, Auctioning); heading-aware retrieval, TEI bge-small, no chat model required. Main-merge GitHub ingestion via POST /v1/docs/ingest; keep last five dataset versions.

## C-06: OAuth and public deployment boundary

- source: P §7.1 shape; §9.2 connector step
- type: api-contract
- content: Code source surface services/desk-gateway is Python/FastAPI, SYSTEMS-owned; infra/desk-gateway is INFRA-owned. Source names reuse OAuth AS/PKCE consent/x-connector-key patterns, not newly chosen architecture here. One desk-<seat> OAuth client per seat with seat:<name> scope, twenty-four-hour access token and thirty-day refresh. Grok Add MCP Server uses https://desk.swcstudio.space/mcp/<seat>. Cross-seat access returns 403. Header-key path is smoke-only. Bind 127.0.0.1:8791; DNS target is the specified VPS address through nginx TLS/systemd. Other existing connector ports remain 7410 (substrate), 8790 (bus), 8789 (claude-cloud); 8787 is occupied. Per-team consent passphrase is held/rotated by Ove, not shared in templates.

## C-07: Contract surfaces, schema and counts

- source: P §7.1 contract; §7.3 counts; §7.4; §11; Appendix A
- type: api-contract
- content: contracts/tool-rosters/<seat>.yaml and contracts/tool-packs/<app>.yaml are QUALITY-owned contract_surface=true. Each tool declares name, JSON schema, backend, g5/g6/read_only tags and consumers. Seven roster consumers are the seven seats; pack consumers are WEB/ANDROID/IOS. Contract PR merges before implementation and breaking changes require G-4 affected-seat acknowledgement. Base roster must have 10–15 gateway tools; source specifies LEAD 15, SYSTEMS 14 and the other five seats 15. Core is eight. Pack is at most five; live seat total at most twenty. Grok host tools and account-wide Marketplace connectors do not count as gateway tools. Additional source-map packs/tools are implementation context, not silent changes to this approved initial scope.

## C-08: Shared core eight tool contracts

- source: P §7.2; REQ-GATEWAY-013–020
- type: api-contract
- content:

| Tool | Observable backend contract |
| --- | --- |
| desk_brief | substrate memory_brief plus open seat tickets; seat/shared Hindsight recall; turn-start call; five-minute Dragonfly cache. Current governance requires classifying sparse and nested errors, not accepting a populated object as success. |
| desk_docs_search | Read-only substrate docs_search through RAGFlow over the desk/substrate/ticket-repo datasets. |
| desk_memory_retain | substrate memory_write→Hindsight retain into pd-<seat>; graph_id/task_id/receipt_path tags; receipt_path or source required. |
| desk_memory_recall | Read-only substrate memory_search→Hindsight recall over own/shared banks, plus lead-reports for LEAD. |
| desk_ownership_resolve | G-1 pre-edit ownership.yaml at origin/main. |
| desk_receipt_check | Compute check_receipt.py/check_secrets.py/check_rollback.py on receipt JSON; no git writes. |
| desk_event_emit | Seat-attributed substrate events_emit. |
| desk_doctor | check/register/install_prompt/repair under C-23 bounds. |

## C-09: LEAD extra seven contracts

- source: P §7.3 LEAD L164; Appendix C; REQ-GATEWAY-021
- type: api-contract
- content:

| Tool | Observable backend contract |
| --- | --- |
| desk_intake_next | LEAD-only pull of the next external desk_intake work order, claiming its row. Appendix C input: `{ type: object, properties: { origin: { type: string } }, additionalProperties: false }`; `origin` is optional and undeclared inputs are rejected. |
| desk_intake_ack | accept/reject/progress acknowledgement back to origin with Graph ID and links. |
| desk_graph_register | substrate graph_register idempotent on Graph ID. |
| desk_graph_state | claim/release/complete via substrate graph_claim/graph_release/graph_complete; mirrors Linear and the Notion Issue row. Appendix C requires graph_id, node_id, action; graph_id pattern ^ut-, node_id ^n[1-8]$, action claim/release/complete. |
| desk_bus_start_job | Lane B through the agent bus; Hermes-only handoff fallback stays handoff_to_hermes. |
| desk_bus_wait_job | Lane B agent-bus wait under the common per-call deadline. |
| desk_roster_status | registration, heartbeat, tool counts and last doctor result, fed by event/rollup status. |

Native Cursor Cloud Agent launch and claude-cloud sessions remain native/other-connector paths, not extra counted gateway tools.

## C-10: SYSTEMS extra six contracts

- source: P §7.3 SYSTEMS L166; REQ-GATEWAY-022
- type: api-contract
- content:

| Tool | Observable backend contract |
| --- | --- |
| desk_index_query | Timescale read-only views. |
| desk_events_query | Bounded read-only Greptime SQL. |
| desk_cache | Dragonfly get/set/del in systems: namespace, TTL ≤24 hours and cache semantics only. |
| desk_lsp_diagnostics | Unified LSP broker: python/go/tsjs Tier-1; rust returns language_not_tier1 until Tier-2. |
| desk_contract_propose | Opens a contract-change PR skeleton under contracts/ from proposal payload; QUALITY merges. |
| desk_design_artifact_get | design/** tokens/specs from origin/main. |

The peer observes an extra SYSTEMS app_tools_load in code. That does not delete or rewrite the source's fourteen-tool requirement; source/code reconciliation is future parent work.

## C-11: WEB extra seven contracts

- source: P §7.3 WEB L168; REQ-GATEWAY-023
- type: api-contract
- content:

| Tool | Observable backend contract |
| --- | --- |
| desk_lsp_diagnostics | tsjs diagnostics. |
| desk_vercel_deployments | Project-scoped list/get. |
| desk_vercel_promote | g5 mutation requiring approval_id and rollback_plan. |
| desk_vercel_rollback | Vercel rollback capability; specific additional gate semantics are not invented where the source is silent. |
| desk_preview_check | Fetch preview and record status plus screenshot hash as evidence. |
| desk_bundle_secret_scan | G-3 over build output. |
| desk_contract_ack | Seat contract acknowledgement. |

## C-12: ANDROID extra seven contracts

- source: P §7.3 ANDROID L170; REQ-GATEWAY-024
- type: api-contract
- content:

| Tool | Observable backend contract |
| --- | --- |
| desk_play_track_status | Read Play Developer API track status. |
| desk_play_staged_rollout | g5/g6 rollout percent and halt threshold with real approval_id and rollback contract; an echoed threshold is not an exercised halt. |
| desk_play_halt_rollout | Halt rollout capability. |
| desk_artifact_size_delta | APK/AAB before/after delta. |
| desk_lint_baseline_diff | Baseline diff. |
| desk_contract_ack | Seat contract acknowledgement. |
| desk_app_tools_load | Ticket-scoped pack load/unload. |

## C-13: IOS extra seven contracts

- source: P §7.3 IOS L172; REQ-GATEWAY-025
- type: api-contract
- content:

| Tool | Observable backend contract |
| --- | --- |
| desk_testflight_status | Read App Store Connect API status. |
| desk_appstore_phased_release | g5/g6 phased-release capability. |
| desk_appstore_pause_release | Pause release capability. |
| desk_entitlements_diff | Info.plist and entitlements between two refs. |
| desk_review_risk_check | Evaluate IOS prompt app_review_checklist against diff, not a fabricated Apple acceptance. |
| desk_contract_ack | Seat contract acknowledgement. |
| desk_app_tools_load | Ticket-scoped pack load/unload. |

## C-14: INFRA extra seven contracts

- source: P §7.3 INFRA L174; REQ-GATEWAY-026
- type: api-contract
- content:

| Tool | Observable backend contract |
| --- | --- |
| desk_railway_status | Both projects' services, latest deployment and health. |
| desk_railway_logs | Bounded redacted logs. |
| desk_railway_variable_names | Names only, never values. |
| desk_railway_redeploy | g5; supplied prior deployment ID is rollback evidence, not itself human authorization. |
| desk_tailscale_status | Forwarders online, mapped ports reachable and ACL self-check. |
| desk_vps_units | systemd status of substrate-*, desk-gateway, vps-agent-bus and grok-claude-cloud. |
| desk_db_health | Greptime/Timescale/Dragonfly/Hindsight health/RAGFlow over tailnet. |

## C-15: QUALITY extra seven contracts

- source: P §7.3 QUALITY L176; G Merge-claim head rule; REQ-GATEWAY-027/036–038
- type: api-contract
- content:

| Tool | Observable backend contract |
| --- | --- |
| desk_gates_run | ci/gates/run_all.py against PR ref in a scratch clone, including --validate-manifest. |
| desk_greptile_review | trigger/get/comments for real review. |
| desk_receipt_approve | Independent receipt approval; refuses bot-06-quality-security self-approval. Original PRD branch stamp is replaced in accepted constraints by C-25's exact-SHA/no-new-tip approval reference, under the explicit assignment. No approval is fabricated. |
| desk_waiver_record | Greptile waiver receipt; withdrawn/head-mismatched waiver is not active. |
| desk_contract_ack_status | G-4 acknowledgements versus contract_consumers. |
| desk_supply_chain_check | License and CVE over lockfile diffs; identifying changed files alone does not satisfy the named checks. |
| desk_secret_scan | check_secrets.py over a ref. |

## C-16: Initial application packs and discovery

- source: P §7.4; §12 n1.4/n4.1/n6.5; REQ-GATEWAY-047–053
- type: api-contract
- content: desk_app_tools_load(app, task_id) loads tools for one ticket and unload=true removes them. Each pack has at most five tools; total at most twenty. Gateway emits notifications/tools/list_changed; Grok client support is not assumed. Fallback serves each at /mcp/<seat>/packs/<app> as a second connector toggled per ticket through Marketplace. WEB uses application packs when needed; mobile seats use specialized application tools. Backend availability and credentials remain external evidence.

| Initial pack | Named tools and source backend semantics |
| --- | --- |
| kanbanos | kanbanos_api_smoke; kanbanos_supabase_query (read-only, project-scoped); kanbanos_push_test (FCM/APNs test device); kanbanos_feature_flags; kanbanos_crash_reports. Backends: KanbanOS API, its Supabase project, FCM/APNs, Sentry/Crashlytics. |
| desklanes | desklanes_api_smoke; desklanes_scoreboard_get; desklanes_push_test; desklanes_store_listing_get; desklanes_crash_reports. Backends: Desk Lanes API and store listings. |
| clippyos | clippyos_api_smoke; clippyos_render_job_status; clippyos_push_test; clippyos_crash_reports. Backend: ClippyOS API. |

The source calls these example tools; n4.1 commits the first three pack contracts. They are retained as the initial specified catalogue, not evidence any product backend exists. Extra discovered coordination/device packs do not broaden this ingest's approved initial pack catalogue or imply their implementation is complete.

## C-17: Intake API and origin-only enforcement

- source: P §10; §7.3 LEAD; §12 n4.4/n6.3
- type: api-contract
- content: POST https://desk.swcstudio.space/v1/intake uses origin tokens (github, slack, recruitment-desk, cron, shortcut), not seat tokens. Body fields are origin/title/ask verbatim/links[]/priority/requested_by/idempotency_key. Timescale desk_intake is queue of record and intake is evented to Greptime. Only LEAD's endpoint exposes intake_next/ack. GitHub issue label desk:intake triggers INFRA's desk-intake.yml to POST its issue URL; acknowledgement comments Graph ID, Linear and Notion links. Slack #programming-desk-intake may trigger intake-poll where supported, otherwise the ten-minute poll covers it. Outside Bots may DM LEAD; build seats hold non-LEAD requests under PD-8. Human mobile actions remain message/mention/approve/watch; advanced setup stays desktop-only.

## C-18: Deadline, failure and refused-tool semantics

- source: P §7.1 failure; §8.1 item 2; §8.2 desk-gateway; §12 n4.3/n6.5; G production loop points 1/6
- type: nfr
- content: Twenty seconds per gateway call. Reads fail open with empty result plus reason; writes and gated tools fail closed. No upstream stack traces to Bots. Unlisted tool does not exist; refusal is a LEAD blocker, not a retry loop. Forwarder-down health is red with no public fallback. Cache-down answers fall through uncached. Wrong seat is 403. Twenty-first tool is refused. Read transport fail-open does not authorize repo editing after a failed/no-revision-marker memory brief. Write timeout does not prove no upstream write happened.

## C-19: Audit and status payload

- source: P §6 events; §7.1 audit; §7.5
- type: schema
- content: Every call audits surface=grok-bot, seat, tool, graph_id, task_id, ok, ms and redacted args hash to Greptime agent_events. Every g5/g6 call requires approval_id/rollback_plan and echoes them into the event. Every desk_brief causes a heartbeat. seat_heartbeat/tool_calls_1m rollups and gate outcomes feed roster status. Langfuse holds LLM traces; gateway does not duplicate them. Read-only status page is explicitly out of scope.

## C-20: Prompt and roster format

- source: P §8.1; §11; Appendix B
- type: schema
- content: Shared and per-seat v1.1 additions use DESK_CHANNEL_ID, SEAT_UUID:LEAD/SYSTEMS/WEB/ANDROID/IOS/INFRA/QUALITY, DESK_GATEWAY_URL and DESK_ROSTER_VERSION placeholders. assemble-prompts.sh --roster grokbot/rosters/<team>.json refuses unfilled placeholders. Source team roster is committed; recipient roster comes from registration. Every seat's source includes tools/memory/connectors/routines sections; tools point at contracts and g5/g6 PD-5, memory specifies own/shared banks/evidence prohibitions, connector preference does not duplicate actions. Always skills are verification-receipts/desk-doctor/desk-bootstrap. LEAD polls held then intake at turn start. The desk-held-poll routine runs every ten minutes unconditionally; only desk-intake-poll may replace its ten-minute schedule with a supported GitHub desk:intake label event.

## C-21: Skill ownership, packaging and activation boundary

- source: P §8.2–§8.3; §11; Appendix A; G production loop point 8
- type: protocol
- content: Skills: desk-bootstrap (LEAD last-match override), desk-doctor (QUALITY), desk-gateway (QUALITY), hindsight-memory (QUALITY), ragflow-docs (QUALITY), platforms/railway-tailscale (INFRA), tool-packs (QUALITY). Source purposes include reading doctor red lines without repairing gates, g5/g6/403/deadline semantics, retain/recall/redaction/reflect discipline, dataset/chunk citation, forwarder cutover/rollback and pack authoring/ceiling. Authoring follows the cited recurring-mistake rule, not speculative skill growth. swc-programming-desk team Marketplace plugin carries skills and seven public connectors; until packaging exists the PRD describes desktop Save-as-skill bootstrap. agent-substrate projector grok-bot target projects /root/agent-skills through the PR-reviewed route, including other-team skills; desk pack proposes back through skills_propose. Current governance forbids seats installing/enabling/editing/publishing/approving skills until skills.approve exists. RW-03 selects the authorized human account owner to review and install/enable through the account UI. Seats remain proposal-only while skills.approve is absent; actual activation/publication evidence remains a runtime gate. No policy waiver or capability is invented.

## C-22: Template and bootstrap surface

- source: P §9.1–§9.2; §11; D-3
- type: protocol
- content: Seven Team-only templates, profile/settings/enabled skills/routines/avatar only. Description has role charter, First run /desk bootstrap and public host only. No UUID/channel ID/XML body/token/tailnet name/receipt, history/memory/credential/computer/group copy. Names use seat labels. Avatar comes from grokbot/avatars. Descriptions are generated, not hand-edited. Routines paused until doctor green; LEAD held/intake polls, seats daily heartbeat. Recipient adds seven in any order, on desktop for connector card, each OAuth desk-<seat> connector; register own UUID; Ove/existing LEAD creates six-seat group and registers channel, excluding QUALITY; all seven plus channel before pinned-tag prompt rendering/install and actual hash report; all seven doctors before unpause. New per-seat memory starts empty with shared environment facts.

## C-23: Doctor acceptance and repair limits

- source: P §9.3; REQ-SHARE-031–038
- type: api-contract
- content:

| Check | Required green evidence |
| --- | --- |
| Prompt | Actual installed SYSTEM_PROMPT.xml SHA-256 equals rendered seat XML at DESK_ROSTER_VERSION; no unfilled placeholder. |
| Skills | Every prompt skill path resolves to private-library name, versions match pinned tag. |
| Memory | Gateway-mediated Hindsight health, own bank existence and redacted retain/recall round trip. |
| Tools | Exact seat contract, base 10–15 or loaded ≤20, all g5/g6 marked. |
| Connector | Valid seat:<name> OAuth and actual cross-seat 403. |
| Roster | Registered channel; actual LEAD membership, QUALITY nonmembership, seven UUIDs, heartbeat ≤24 hours. |
| Substrate | desk_event_emit persisted in Greptime and docs search hit for verification receipt. |

Doctor reports, never edits gate/receipt/another seat's file. Repair only reruns prompt install/connector re-auth. Caller-supplied hashes or asserted membership are not independent evidence of actual installed files/group membership.

## C-24: G-7 authored-integrity targets

- source: P §11 G-7 L308; §12 n5.1
- type: nfr
- content: G-7 fails base roster counts below ten/above fifteen, missing tool schemas, missing approval/rollback fields on g5/g6 tools, literal UUID/channel IDs in source prompts, unfilled placeholders in assembled prompts and token-shape/tailnet names in templates. Integrate check_desk_integrity.py into run_all.py and test_gates.py fixtures. Parent's source map reports narrower current checks (including g6-only field handling and placeholder/missing-template gaps); that gap is not accepted as the target or proof of template publication.

## C-25: Exact-current-SHA independent approval without a new tip

- source: P §7.3 QUALITY/§9.4/§12 n6.2; G Merge-claim head rule L202–250; explicit assignment
- type: protocol
- content: Receipt approval must bind independently to the exact SHA actually read and must not create a new SHA. Receipt carries approval_ref kind (check_run/pr_review/gateway_store), name and reviewed_sha. G-2 resolves it against current head and passes only actual approval for that SHA. Preferred source-specified mechanism is check run head_sha; PR review and gateway record keyed by (receipt_path, reviewed_sha) are permitted fallbacks. No mechanism is selected or implemented by this worker. Greptile must be COMPLETED for that same head; missing/moved/SKIPPED/withdrawn/mismatched evidence blocks merge_claim.allowed. No placeholder approved_by. Claims cite evidence_command_index. The PRD on-branch stamp is preserved as documentary discrepancy; the assignment authorizes the exact-SHA/no-new-tip constraint, not an inferred temporal override.

## C-26: Production-loop brief and revision semantics

- source: G production loop points 1–3 L54–100
- type: protocol
- content: No repo edits/commits/branches/pushes/PR/write-tool work before a successful brief under the desk-seat policy. Reading is allowed. Shape A top-level error/reason with no substrate/recall means call never ran (unknown_tool/deadline/forbidden/invalid_args/secret_refused/backend_missing/internal). Shape B populated brief can hide substrate.error, recall.error or recall.results[].error; one failed bank fails the brief. desk_brief has no etag: record generated_at as brief_read_at and cached absent=false; generated_at is not revision identity and cache may lag memory by five minutes. A successful no-marker brief still requires brief_no_revision_marker ack. An actual etag, when supported, is brief_etag. QUALITY G-4 revision-marker correction is a stated contract gap, not assumed landed. This ingest worker is not executing a Grok seat ticket loop or claiming memory-plane success.

## C-27: Human turn acknowledgements versus destructive approvals

- source: G production loop point 3 L81–100
- type: schema
- content: brief_degraded and brief_no_revision_marker are unknown, not none. Human acknowledgement names degraded-loop: repo work without a memory brief or the corresponding operation on a brief with no revision marker. Build seat asks LEAD priority-false; LEAD asks Ove 1:1. Ack covers one turn/one ticket, goes in loop_acks never approvals[], and cannot serve as g5/g6 approval_id or be typed by the requesting seat. unverified records verbatim diagnostic and field path, naming the failed bank for per-bank reason. No acknowledgement is a blocker; reporting a blocker completes the stopped turn.

## C-28: Event catalogue and degraded-turn payload

- source: G production loop points 4–5 L101–116
- type: schema
- content: Completed acknowledged degraded work emits implementation.completed with receipt path and payload.degraded, blocker, upstream_reason, reason_path and ack ID. Stopped work emits ticket.blocked. Do not collapse code/diagnostic into a single reason. Current gateway emits top-level kind=note and catalogued kind in payload.event; current routing field is payload.event, not proof any consumer routed it. Caller payload must not overwrite seat/event/task_id. QUALITY owns the G-4 contract resolution between kind passthrough and documented payload.event routing; no arbitrary variant is selected in this ingest.

## C-29: Non-atomic retain and retry evidence

- source: G production loop point 6 L117–124
- type: protocol
- content: desk_memory_retain may return ok=true when only one of Hindsight/substrate accepted. Inspect results per plane and record partial write in unverified. Timeout may follow commit. Only local evidence_required/secret_refused proves no upstream call. Roster has no idempotency-key input; uncertain write is recalled before at most one retry with possible duplicate stated. This is bounded handling for the existing tool, not a new retry system.

## C-30: Ownership and human-visible coordination

- source: P §11; Appendix A; G Flow/Lane C ticket flow/Channel rules/Channel discipline/Direct-from-Ove and widgets
- type: protocol
- content: QUALITY owns contracts/shared directives/assembly/gates/broad docs and skills unless last-match override; SYSTEMS owns gateway; INFRA owns infra/workflows and platform networking skill; each seat owns its prompt; LEAD owns grokbot and desk-bootstrap. Ticket paths stay owned. Contract-first via QUALITY precedes cross-seat tickets. LEAD is orchestrator, not implementer. Assignment is LEAD→seat SendToAgent 1:1; Desk is human-visible status, not the assignment bus. Each dispatch has Desk audit note. Build results label awaiting-review / pending QUALITY and send receipt priority-false; QUALITY stays off-channel to LEAD priority-false, LEAD relays. LEAD polls held messages at turn start/after Desk activity. Reports to Ove are 1:1; widgets there only, numbered text in group, selection echoed in group and priority-true to requesting seat. Direct Ove asks to build seat require held plan and LEAD response before edit.

## C-31: Source-defined rollback and reporting

- source: P §12 n7.1–5; §5 rollback; G Verification
- type: protocol
- content: Existing source order n2→n3→n4→n5→n6 with skeleton overlap only; n7 depends on n2–n6. Network rollback deletes forwarders/recreates proxies/domain; substrate env restores by file; gateway additive removal leaves prior Bots minus new tools; prompts reassemble v1.0 with committed roster; templates republish. Desk cutover announcements/dispatch notes, actual PR-field sync to Notion/Linear and Ove 1:1 report include receipt paths/every unverified. Superseded railway-app retirement occurs after n6 with G-6. Runtime lanes n2/n5 Lane C; n3/n4 default Lane A, Lane B only if Ove asks. No rollback is claimed exercised.

## C-32: Evidence, handoff and no fabricated clearance

- source: P opening status/§13 final paragraph/§12 runtime lanes; G production loop paragraph L133–136/Verification/Merge-claim head rule
- type: protocol
- content: Source authoring statements and historical receipts prove only their named scope. Fresh Bot/real mobile/network/public reachability/current independent approval remain separate from fixture/unit/source proof. Signed handoff schema is documented unlanded in governance (SPE-4792); absent packet fields are omitted and unsigned status recorded, never invented. This omp delegation is not a bus task.assign and no signature is claimed. No secrets, credentials, reviewer stamps or deployment state are manufactured. D-4's no-merge restriction is authoring-session-scoped. The user explicitly chose Create planning setup; core planning artifacts are authorized, not runtime implementation or clearance and tests/gates/lint/build/formatters are skipped by assignment.

## C-33: User-resolved weekly reflect cadence

- source: P §6 memory L127; §8.2 hindsight-memory
- type: nfr
- content: Original §6 wording competed between nightly and weekly reflection, reinforced by the weekly hindsight-memory skill. RW-01 records the user's Weekly reflect selection. REQ-DATA-013 and REQ-DATA-014 retain stable IDs and now require coherent weekly mental-model reflection/pruning with forever-retained verified facts; no nightly or split-bank schedule. Source discrepancy is historical provenance, not an open warning.
