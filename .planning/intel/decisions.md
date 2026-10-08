# Desk v2 — Staged Decisions

- task_id: SynthesizeDeskV2Intel
- correlation_id: desk-v2-autonomous-2026-10-08
- status: STAGED_NOT_VALIDATED
- source: [docs/upgrade-plan-desk-v2.md §3](../../docs/upgrade-plan-desk-v2.md#3-decisions-locked-with-ove-2026-09-30), L43–50

The approved source PRD explicitly records locked operator decisions. Its document-level PRD classification and original draft/proposal header do not erase those explicit decision locks. No replacement ADR, invented approval or inferred date ordering is used. Three locks constrain the continuing feature; D-4 is also preserved verbatim in meaning, with its stated original-authoring-session scope. No competing locked decision was found in the two ingested domain sources.

## D-1: Fixed five-service placement

- source: docs/upgrade-plan-desk-v2.md §3 D-1, L47; §6; Appendix D
- status: locked
- decision: Ultrathink contains GreptimeDB, TimescaleDB and DragonflyDB; Agent Substrate contains Hindsight and RAGFlow. Hindsight replaces Agentmemory in the substrate memory phase.
- scope: service allocation and data-plane responsibilities; REQ-INVENTORY-004, REQ-DATA-001–038

This does not mean these projects have only these services. Parent inventory reports other services too. A similarly named project in a connected account is not proof its owner is Ove or that mutations are authorized. Neither extra inventory services nor existing source files reopen the five-service choice.

## D-2: Bots use the VPS gateway; Railway uses per-project forwarders

- source: docs/upgrade-plan-desk-v2.md §3 D-2, L48; §4 rules 2–3; §5
- status: locked
- decision: Bots reach Railway through the Desk Gateway on the VPS, never by joining the tailnet. The VPS reaches Railway services over Tailscale Forwarders inside each Railway project. Bots hold no database credentials; public database proxies/domains retire after the verified cutover.
- scope: transport and credential boundary; REQ-NETWORK-001–020, REQ-GATEWAY-004–012, REQ-DATA-037

The observed railway-app subnet-route advertiser is inventory, not the prescribed forwarder proof. Public-health success is not tailnet-cutover proof. Current source gaps and documented historical public fallback do not authorize a public fallback after cutover. RW-02 resolves the original administrative-device discrepancy to VPS plus Ove's Mac mini and XPS with exact mapped ports and deny-by-default; it is not permission to let Bots join the tailnet or downgrade D-2.

## D-3: Seven Team-only seat templates with bootstrap and doctor

- source: docs/upgrade-plan-desk-v2.md §3 D-3, L49; §9.1–§9.4
- status: locked
- decision: The share consists of seven Team-only templates, one per seat, a desk-bootstrap skill recreating the group/connector/prompt, and desk-doctor proving integrity. Templates carry no secrets, UUIDs or internal URLs beyond the public gateway host.
- scope: share and fresh-desk acceptance; REQ-SHARE-008–040, REQ-ACCEPT-001–019

Generated Markdown is not a published Team-only template; referenced avatar paths are not actual avatars. A fresh recipient is required. The plan does not depend on one Bot creating another Bot. RW-03 selects authorized human account-UI review and installation/enablement; actual activation/publication evidence remains required, not an implicit waiver of this lock or authority for a seat to self-install.

## D-4: Original authoring-session publication boundary

- source: docs/upgrade-plan-desk-v2.md §3 D-4, L50; opening status L3–4; §13 final paragraph L349
- status: locked
- decision: The original plan-authoring session lands a draft programming-desk PR, a shareable document and a companion agent-substrate draft docs PR, with no merge, tracker rows or deploys from that authoring session.
- scope: the original plan-authoring session, not a newly invented indefinite ban on the user's selected initialization/execution

The user selected initialization from this source plan, resolved W-01/W-02/W-03, then explicitly chose “Create planning setup”. This bootstrap creates core planning artifacts only, without implementation, tracker mutation, deployment, commit or push. These boundaries come from this assignment, not a reinterpretation of D-4. Routing approval is not runtime authorization or independent exact-SHA review.

## Approval mechanism reconciliation — not a new locked decision

- source: docs/upgrade-plan-desk-v2.md §7.3 QUALITY L176, §9.4 L276, §12 n6.2 L326; docs/desk-operating-model.md Merge-claim head rule L202–250; authenticated assignment's exact-SHA/no-new-tip instruction

The PRD says desk_receipt_approve stamps approved_by on the PR branch. Current governance explicitly explains why approval-as-commit moves the head out from under Greptile's reviewed SHA and specifies approval_ref resolved against current head, with no new tip. The assignment explicitly requires the latter. Synthesis therefore preserves the original branch-stamp statement as a documentary discrepancy, while retaining independent QUALITY approval as the acceptance intent and applying the current exact-SHA/no-new-tip constraint to its delivery. This is an explicitly authorized constraint reconciliation, not an invented claim that one source is temporally newer or that a lock was superseded.

Approval implementation and real independent reviewer evidence remain unverified/missing according to the parent source map. No approved_by value, approval_ref record, human acknowledgement or signature is manufactured. See REQ-GATEWAY-036–038, REQ-ACCEPT-006 and INFO I-01 in [INGEST-CONFLICTS.md](../INGEST-CONFLICTS.md).
