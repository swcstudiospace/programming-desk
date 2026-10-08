# Desk v2 — Ingest Synthesis (Staging Only)

- task_id: SynthesizeDeskV2Intel
- correlation_id: desk-v2-autonomous-2026-10-08
- capability: requirements source classification/synthesis under authenticated parent omp delegation
- status: STAGED_NOT_VALIDATED; complete staging deliverable, not implementation/phase/release clearance
- core-routing gate: USER APPROVED “Create planning setup” after resolving W-01/W-02/W-03; no runtime or review clearance

## Source set and authority

Two domain documents were read completely, including raw rereads of long source lines:

1. [docs/upgrade-plan-desk-v2.md](../../docs/upgrade-plan-desk-v2.md) — **PRD**, explicitly designated by the user as the approved full source proposal. Its original draft/no-built-work header is historical evidence, not a reason to ignore locked decisions or omit apparently authored requirements.
2. [docs/desk-operating-model.md](../../docs/desk-operating-model.md) — **SPEC** for its current normative production-loop/receipt/approval protocols, with its operating/channel prose also retained as context. The assignment explicitly names it as governance evidence; no temporal ordering is invented.

Domain counts: PRD 1, SPEC 1, ADR 0, DOC 0, UNKNOWN 0. The [conflict engine](/root/.agents/gsd-core/references/doc-conflict-engine.md) is a process contract, not a third product specification. The ingest workflow was read for staging/core-routing separation. Other referenced policy and companion documents were not recursively imported or declared validated.

The two-document in-set reference graph has the source PRD pointing to governance and no reverse plan reference in the read governance text. No in-set cycle or competing locked source decision was found. Parent/peer runtime and source-map evidence is attributed separately and bounded to what it actually covers.

## Intelligence inventory

- **Source decisions:** four explicit locks preserved: D-1/D-2/D-3 constrain the continuing feature; D-4 remains the explicit original-authoring-session restriction. No lock was downgraded because the overall source was a proposal.
- **Requirements:** 217 retained target rows with deterministic grouped REQ-* IDs, source-section/line references, Given/When/Then acceptance and existing-node/step mapping. AC-* IDs derive by replacing the REQ-* prefix. No row is dropped because code, Markdown or an old receipt exists.
- **Constraints:** 33 source-derived entries: 13 api-contract, 6 schema, 5 nfr, 9 protocol. They preserve all named seat/core/pack tool semantics, store/retention boundaries, prompt/template/doctor checks, failure/gate/security behavior and current governance gaps. They are extracted source mechanisms, not a new architecture design.
- **Context:** six topics covering source authority/history, authored-surface limits, bounded parent runtime, bounded peer maps, cross-repo/human responsibilities and protected zones/non-goals.
- **Delivery trace:** every one of the 41 source steps, all seven nodes, all §5–§11 invariant sections and Appendices A–D mapped in the structured classification. All seven full phases remain UNVERIFIED.

## Existing seven-node graph coverage — not a new roadmap

| Source node | Retained group | Requirements | Source steps | Evidence boundary |
| --- | --- | --- | --- | --- |
| n1 understand — inventory | INVENTORY | 16 | n1.1–n1.6 | Parent has real service listener and railway-app identity evidence; Bot write/client notification/team policy/authorization/document-update closure is not proved. |
| n2 decompose — network | NETWORK | 22 | n2.1–n2.6 | Includes both forwarders, identity/keys, exact-port ACL/VPS/Mac probes, five-service env cutover, brief/events verification, G-6 exposure retirement/rollback and receipt. No cutover proof. User-selected VPS plus Mac mini and XPS scope; original discrepancy retained as provenance. |
| n3 generate — substrate | DATA | 38 | n3.1–n3.6 | Includes companion docs/GSD replan, complete Hindsight migration/banks/redaction/version, Dragonfly cache-only/TTLs/fail-through, Timescale tables/queue/claims/idempotency/hypertables/retention, RAGFlow ingest/search, event ledger/anchor and package receipts. External owner work remains required. |
| n4 generate — gateway/contracts | GATEWAY | 54 | n4.1–n4.6 | Includes all eight core tools, every seat-specific source tool, OAuth/scopes/counts, contracts/acks, all-call audit, g5/g6 fields/real authorization, twenty-second failures, intake entry routes and three initial mobile packs/ceilings/fallback. Local gateway availability is not full implementation or public-client proof. |
| n5 refine — prompts/skills/share | SHARE | 40 | n5.1–n5.6 | Includes all prompt placeholders/sections/assembly/G-7, seven skills, team plugin/shared projector/proposal, seven generated and actually published Team-only templates/avatars/screenshots, all bootstrap steps and seven doctor checks. Publication and lifecycle authority are not inferred. |
| n6 critique — fresh acceptance | ACCEPT | 34 | n6.1–n6.6 | Includes fresh recipient, docs-only double-uplift/ticket/pending result/current independent approval, roster events, real GitHub and curl intake, iOS push approval, five failure drills, bounded questions and every current production-loop/channel evidence rule. Existing Bots/unit fixtures do not substitute. |
| n7 synthesize — rollout/rollback | ROLLOUT | 13 | n7.1–n7.5 | Includes the source dependency order/allowed skeleton overlap, five rollback surfaces, cutover announcement/audit notes, PR-tracker sync/Ove report and conditional post-n6 G-6 node retirement. No exercised rollout/rollback is claimed. |

Cross-repo boundaries are preserved, not silently cut: agent-substrate owns the companion data/docs/migrations/adapters/projector work; agent-skills owns reviewed skill proposals/library changes; real platform/runtime owners provide credentials, lifecycle and configuration migration evidence. Only staged intel is written in this repository.

## Conflict gate and documentary discrepancy

Read [INGEST-CONFLICTS.md](../INGEST-CONFLICTS.md) verbatim for the contract-shaped report:

- **BLOCKERS: 0** — no selected-source absence/UNKNOWN/cycle/competing locked decision. This is not a runtime-readiness assertion.
- **WARNINGS: 0** — the user resolved W-01 to Weekly reflect, W-02 to Mac mini and XPS (with VPS, exact mapped ports and deny-by-default), and W-03 to authorized human account-UI activation. Stable IDs now carry coherent active acceptance; original nightly/Mac-mini-only/seat-activation discrepancies remain provenance, not live alternatives.
- **INFO: 12** — three user-resolved discrepancies RW-01/RW-02/RW-03 plus the nine existing INFO records, including exact-SHA/no-new-tip approval and D-4 authoring-session scope.

The approval discrepancy is explicit: PRD §7.3 QUALITY, §9.4 and §12 n6.2 say to stamp approved_by in the branch; governance's Merge-claim head rule says the approval must bind to the actual reviewed SHA and must not create a tip, using an externally resolvable approval_ref. The assignment expressly mandates that constraint. Independent approval remains the acceptance intent, but a branch-stamp commit is not the accepted delivery mechanism. This resolution does not manufacture temporal precedence, supersede D-1/D-2/D-3 or supply reviewer approval. The peer reports the code still lacks that contract. No stamp/reference/signature is created.

No warning was auto-approved. The actual user supplied all three resolutions and separately chose “Create planning setup”. Core artifacts are authorized; all seven phases remain incomplete/unverified and human/runtime gates remain intact.

## Environmental prerequisites are separate from ingest blockers

Parent evidence is in local://desk-v2-runtime-evidence.json and summarized with attribution in context.md:

- Healthy loopback gateway, seven endpoints/three packs, but **no registered seats/channel**.
- **Bot computer offline**, planned named forwarders absent, **public gateway DNS reader/local resolver failed**.
- Substrate active but **healthz HTTP 503**, index/Greptime/eventsWritable false.
- railway-app **really identified** as Ultrathink/production/tailscale-vpn and observed advertising subnet routes; not a verified required forwarder or authorization to retire it.
- **Actual LISTEN ports** for all five services, not default-port guesses; extra 4002/9382 are inventory, not added target mappings.
- Public Hindsight healthy/database-connected, configured image 0.9.1; **no tailnet/bank/version/embedding/write-read doctor proof**.
- Connected account authorization as Ove, Cursor policy/tier, Bot path/client notification, publication, fresh recipient/mobile and independent reviewer evidence remain unestablished.

These are execution-blocking prerequisites, not absent PRD inputs. Documentary staging is complete despite them; runtime phase completion is not. No parent observation is rerun here. Peer source-map gaps (JSON authority, untrusted approval strings, incomplete approval/doctor/data/plugin/share behavior) are implementation gaps, not weakened acceptance or permission to omit source scope.

## Output map and parent hand-off

The complete staging output is exactly:

- [classifications/desk-v2.json](classifications/desk-v2.json): source types, explicit decision evidence, source-invariant crosswalk, every node/step, requirement ranges, conflict classification and output boundary.
- [decisions.md](decisions.md): D-1/D-2/D-3/D-4 preserved with scope and documentary approval discrepancy.
- [requirements.md](requirements.md): 217 normalized active target rows and atomic observable acceptance.
- [constraints.md](constraints.md): 33 technical/governance source constraints and full tool/doctor catalogue.
- [context.md](context.md): attributed runtime/source evidence, responsibility/human gates and protected scope.
- This SYNTHESIS.md: entry point, not a roadmap.
- [../INGEST-CONFLICTS.md](../INGEST-CONFLICTS.md): exactly BLOCKERS/WARNINGS/INFO buckets, no report tables.

Parent next actions: continue Phase 1 discovery/discussion; route cross-repo/owned-path work and actual human prerequisites; run consolidated verification after all artifact slices land. User conflict and core-routing choices are recorded, not pending. This bootstrap runs no validation or runtime operation.

## Verification and protected destinations

No build, lint, test, gate, formatter, smoke, deployment, git commit or push was executed by this worker. Python/Bun req_lint are explicitly skipped by the assignment; artifacts are not marked VALIDATED. Source reads and successful writes establish only extraction and artifact creation. Historical receipt claims and parent probes retain their stated evidence boundaries.

Core PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md and config.json are produced under the explicit user routing choice. No implementation, other-repository write or phase PLAN/SUMMARY is produced. Unrelated web/desk3d remains untouched; no credentials, human acknowledgements, approvals, signatures or completion evidence is fabricated.
