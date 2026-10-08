# Desk v2 — Staged Context and Evidence Boundaries

- task_id: SynthesizeDeskV2Intel
- correlation_id: desk-v2-autonomous-2026-10-08
- status: STAGED_NOT_VALIDATED
- authorization: the authenticated parent omp delegation carries the user's selection Initialize from Desk v2 plan. It is not an AgentSwarm bus task.assign; no .swarm row, bus signature or reviewer approval is asserted.

## Source roles and historical statements

- source: [docs/upgrade-plan-desk-v2.md](../../docs/upgrade-plan-desk-v2.md), opening L3–9, §1–§3, §12–§13; explicit assignment

The user-selected PRD is the complete source for the feature, including all seven delivery nodes, their 41 source steps and every §5–§11 invariant. Its original header says draft proposal and no built/deployed/verified work from the authoring session. That is source history, not evidence all current code is absent and not a reason to reduce scope. Explicitly locked D-1/D-2/D-3 remain final; D-4's restriction has its explicit original-session scope. The verbatim operator ORIGINAL remains at §1 for the first uplift; this synthesis does not replace it with a new ask.

- source: [docs/desk-operating-model.md](../../docs/desk-operating-model.md), Flow, production loop, Verification, Merge-claim head rule, Channel discipline

The governance source contains technical protocol constraints, not merely background prose: nested brief-failure detection, revision-marker acknowledgement, non-atomic memory writes, event-routing limitations, skill activation authority and exact-SHA/no-new-tip independent approval. It is classified SPEC for these normative sections. Other channel/operating prose is retained as contextual evidence. No assertion that its date beats the PRD is made. The assignment explicitly names it as current governance and explicitly mandates exact-SHA approval.

- source: /root/.agents/gsd-core/references/doc-conflict-engine.md Severity Semantics / Report Format / Safety Gate; /root/.agents/gsd-core/workflows/ingest-docs.md synthesize / conflict_gate / route_new_mode

The conflict engine is a process contract, not another feature PRD. Only BLOCKERS/WARNINGS/INFO are report buckets; reports use Found and Expected/Impact/Note, with remediation for blocker/warning entries. Staging intel survives a paused gate. The user resolved all three warnings and explicitly chose Create planning setup. Core planning generation is now authorized; runtime implementation and all validation gates remain separate.

## Original inventory versus implementation evidence

- source: docs/upgrade-plan-desk-v2.md §2 and §13; agent://MapGatewayDelivery/report; agent://MapShareAndNetworkDelivery/report

The PRD's today table is explicitly its 2026-09-30 authoring inventory: seven hardcoded Bot identities/channel, source assembly, 17 skills, no Grok Bot projection, root CI absent, public DB connectivity and planned/owner-skipped data work. These source statements remain provenance, not current runtime facts. The read repository root contains newer gateway/contracts/infra/skills/templates/workflow surfaces. Peer source maps report root CI wiring, prompt/shared-directive changes and implemented local gateway paths. Authored surfaces correct file-existence claims, but do not prove deployment, active branch protection, seven real templates, private skill installation or fresh-desk acceptance. Every requirement remains retained and every phase remains unverified for full milestone completion.

## Parent-observed runtime snapshot

- source: local://desk-v2-runtime-evidence.json, recorded_on=2026-10-08, baseline_commit=4f8e495e4eba1a799056adf3d4385522c59df359; parent coordination messages
- evidence_kind: parent-observed reads, not commands re-executed by this agent; no mutations or independent approval

The exact baseline SHA is provenance for the supplied observation, not a claim this staged edit is independently approved or that the branch cannot subsequently move.

Observed facts:

- Gateway loopback GET http://127.0.0.1:8791/health reports ok, version 0.1.0, seven seat endpoints and clippyos/desklanes/kanbanos packs. systemd is active. registered_seats=[] and channel_registered=false. This is local availability, not OAuth/bootstrap/doctor/share success.
- Public https://desk.swcstudio.space/health reader failed DNS ETIMEOUT; getent ahostsv4 desk.swcstudio.space exited 2 with no output. This bounds public reachability to the observed failed reader/local resolver; no wider DNS-state or propagation claim is invented.
- tailscale status --json exited 0: VPS and Mac mini online; grok-bot-box offline, last seen 2026-10-02T02:45:28.1Z; the two planned named forwarders absent.
- railway-app is online at 100.77.7.42 advertising 10.128.0.0/9 plus the reported Railway IPv6 routes. Railway SSH printenv TAILSCALE_HOSTNAME exited 0 with railway-app for Ultrathink/production/tailscale-vpn, source Andrew-Bekhiet/railway_tailscale_vpn. This is genuine node/project identity evidence and a subnet-route-advertiser observation, not verified per-project-forwarder mapping or authority to retire it.
- Railway listener/configuration reads confirm Greptime ports 4000/4001/4002/4003; Timescale 5432; Dragonfly 6379; Hindsight 8888; RAGFlow 9380/9382/80. Dragonfly kernel tcp record 00000000:18EB state 0A means LISTEN on 0.0.0.0:6379; ss was unavailable, and the kernel-record fallback supplied the positive port evidence. No service port is claimed proven by empty filtered logs. Additional listeners are inventory, not approval to add forwarder/ACL mappings.
- Timescale public TCP proxy and Greptime public HTTP domain remain present in the supplied Railway inventory. No exposure retirement or rollback is observed. Agent Substrate's supplied service inventory has no forwarder service.
- The connected Railway account has projects with matching names but its identity is not established as Ove's. Actual project/environment/service IDs are in the parent snapshot; ownership/authorization must be confirmed before mutations. Matching names do not authorize action.
- The Hindsight configured Railway image is ghcr.io/vectorize-io/hindsight-api:0.9.1, whereas the plan mentions template v0.10.1-slim as an assumption. Public Hindsight /health reports healthy/database connected. Neither fact proves the API compatibility gate, embedding dimensions, dedicated bank, VPS tailnet path or retain/recall doctor round trip.
- substrate systemd is active, but GET http://127.0.0.1:7410/healthz returned HTTP 503, index=false, greptime=false, eventsWritable=false (appendOnly=null). Service activity is not a successful brief, persisted event or database health proof.
- Cursor browser relay inspection timed out after 12000 ms and left no managed tabs. Team tier/network policy remains unobserved; no absence of access policy is inferred.

These are execution-blocking prerequisites for the affected n1/n2/n3/n4/n6 behaviors, not missing input documents or locked-decision contradictions. They do not prevent documentary staging. They do prevent honest claims that full phases, doctor, cutover or release are complete. The parent did not exercise Bot UUID/prompt writes, tools/list_changed, team policy/tier, forwarder deploy/cutover, database mutation, template publication, fresh-desk/mobile acceptance or independent reviewer approval.

## Peer source maps — bounded, second-hand code evidence

- source: agent://MapGatewayDelivery/report; underlying programming-desk locations cited in that report, not independently reread by this worker

Gateway source has real seat routing, OAuth, JSON contract loading and API paths, but local JSON Store is the authority for intake/roster/packs/acks/doctor rather than the required Timescale transaction layer. Pack task_id is recorded but ticket-close expiry is not implemented in the inspected source. Early validation/refusal paths are not all audited to Greptime. schema validation omits some declared constructs. Doctor trusts caller-supplied hashes/skills and hardcoded membership assertions, so green output alone cannot prove installed prompt or actual group membership. Runtime approval_id is checked as a field/string, not real authorization; receipt approval still commits a stamp with race protection but no approval_ref exact-SHA binding. supply_chain_check does not perform the promised license/CVE lookup. Missing extra mobile backend modules and product-route prerequisites are bounded to the inspected catalogue and do not silently expand this PRD's initial three-pack scope. No live connector or platform mutation is proved.

- source: agent://MapShareAndNetworkDelivery/report; underlying programming-desk locations cited in that report, not independently reread by this worker

Forwarder specs/ACL/installers and generated template descriptions are authored surfaces, not deployed/publication receipts. The inspected ACL's 4000–4003 range includes an unmapped 4002; existing network examples omit some mapped-port probes, so they cannot prove exact-port verification. Historical substrate docs retain a public fallback that must not become the no-public-fallback post-cutover target. Gate workflow exists at the root, but current runner/branch-protection/green-run evidence remains separate. Intake workflow still requires its real secret/public route/runner capacity and label-event acknowledgement evidence. Prompt source/assembly/G-7 are partial relative to the source's exact parsing/placeholder/all-seat expectations. Seven Markdown descriptions exist, but inspected avatar directory has only .gitkeep and no Share-card/publication proof, plugin manifest/publication receipt or skill proposal result was found in the bounded paths. Current-source G-7 is narrower than the target and does not prove share publication. No exercised full-node rollback, cutover announcement, current tracker sync or railway-app retirement receipt was found in those paths.

- source: agent://MapCompanionDataDelivery/report; underlying agent-substrate locations cited there, read-only peer investigation, no edits by this worker

Companion source has Hindsight/RAGFlow read transports and PG graph/memory indexing, but no evidenced complete Hindsight retain/bank/version path, integrated Dragonfly caches/counters/fail-through, Desk tables/hypertables, RAGFlow redacted ingest/dataset/citation pipeline or Grok Bot plugin projector in the scoped packages. Its existing projector emits env fragments, not installed plugin evidence. Historical archival/stub/fixture claims do not satisfy Desk phase closure. No deep import/copy of those incomplete clients is proposed here; target remains source-specified substrate API boundary and external owning-repository work.

## Cross-repo and human responsibility ledger

- source: P §5–§11, §12 n1–n7, Appendix A/Appendix D; G Lane C ticket flow / ownership / approval rules

programming-desk responsibilities:

- LEAD: source kickoff/double uplift, concrete tickets and integration, grokbot roster/descriptions/avatars/templates, desk-bootstrap ownership, fresh-recipient coordination, cutover announcements, PR/tracker sync and Ove 1:1 reporting.
- QUALITY: contract surfaces/consumer acknowledgements, shared directives, assembly/G-7/gates, broad docs/skills with named overrides, independent review/approval. It stays off-channel, cannot self-approve its own receipt and does not manufacture clearance.
- SYSTEMS: gateway source and seat/core/pack/intake interfaces under contract, not unauthorized edits to other seats' paths.
- INFRA: gateway deploy/DNS/TLS/systemd, Railway forwarder and tailnet policy, environment cutover/exposure changes, workflows and networking platform skill.
- Every seat: its own prompt, assigned paths, production-loop evidence, held receipt handoff and honest unverified lists.

External repository/runtime responsibilities:

- agent-substrate SYSTEMS/owners: companion data/network docs, .env.example/README/Data section, GSD replanning of existing substrate phases, real Hindsight/Dragonfly/Timescale/RAGFlow behaviors and grok-bot shared-skill projector; per-package receipts. No file in that repository is written here.
- agent-skills reviewers/maintainers: review skills_propose PR for the desk pack and shared mined skills. Read-only shared checkout is not permission to modify it or evidence a proposal merged.
- Existing claude-cloud connector supplies source OAuth/PKCE patterns; existing bus/substrate/LSP/product services supply dependencies. Their names in the plan are not proof their needed contracts/credentials are configured.
- Claude Code/Hermes runtime owners: back up then retire local hindsight stdio/set Hermes provider none as source-directed migration; this is not permission for this staging worker to edit their configuration.

Human/external approval ledger:

- Ove or the authorized account owner: establish Railway ownership/authorization and team setup. W-01 is resolved to Weekly reflect, W-02 to VPS plus Mac mini and XPS with exact-port deny-default grants, and W-03 to human-reviewed account-UI installation/enablement. Actual activation, publication and all runtime authorization remain required.
- Ove: per-team passphrase/rotation, optional public hindsight-ui choice, real G-5/G-6 approvals and rollback plans including exposure removal/retirement; these are never synthesized from strings or audit events.
- Fresh recipient: actual seven-template add/bootstrap/installed prompt/skills/group evidence.
- Ove with real iOS: mobile message and push-notification g5 approval evidence.
- Independent QUALITY/reviewer: current exact-SHA approval through no-new-tip reference, current Greptile COMPLETED evidence and authentic waiver status; older stamps or scores do not cover a moved tip.
- Parent: continue Phase 1 discovery/discussion, route external owning-path tasks and perform consolidated verification after both artifact slices land. The actual user conflict resolutions and explicit Create planning setup routing choice are recorded; this worker runs no checks.

## Explicit non-goals and protected zones

- source: P §7.5; D-4; assignment target/change/acceptance; authenticated parent contract

No read-only status page in v2; no Bot tailnet enrollment; no data-store source-of-truth replacement; no durable Dragonfly queue/session/lock/pubsub; no dependence on Bot-created Bots; no broadened mobile-device-pack implementation inferred from peer discoveries. Full approved n1–n7 scope remains active.

The seven original staging artifacts are normalized and the four root core artifacts plus config.json are initialized under explicit user routing approval. Phase 1 directory files and intel/implementation-map.md belong to the evidence worker; they are referenced by fixed durable paths without reading incomplete output. No implementation, test, tracker row, deployment, commit, push or other-repository edit occurs here. Unrelated web/desk3d remains untouched; no VALIDATED or gate-pass claim is made.
