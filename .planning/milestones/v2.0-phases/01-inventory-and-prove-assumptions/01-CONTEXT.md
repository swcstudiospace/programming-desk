# Phase 1: Inventory and prove assumptions - Context

**Gathered:** 2026-10-08
**Status:** Ready for research and planning; not executed or verified
**Mode:** Autonomous smart discussion. The source fixes the inventory boundary; the user resolved the three material documentary choices and explicitly approved core routing. No additional design preference is inferred from missing runtime access.

<domain>
## Phase Boundary

Establish the approved source's n1 inventory and assumptions, including its kickoff provenance/tracker links and REQ-INVENTORY-001 through REQ-INVENTORY-016. Preserve the complete original operator ask, seven source nodes and 41 source steps. Record the five mapped Railway services and railway-app identity, actual Bot UUID and writable prompt path, actual MCP-client notification/fallback behavior, Cursor policy/tier, prerequisite availability and the QUALITY-owned §13 update. This phase does not deploy forwarders, change ACLs, retire public exposure, migrate data, publish templates or certify downstream acceptance.

</domain>

<decisions>
## Implementation Decisions

### Evidence and phase gates
- **D-01:** Reuse the bounded, parent-observed inventory in `01-INVENTORY.md` and `01-INVENTORY.json`; preserve observed/configured/unverified distinctions. Actual service listeners and the railway-app identity are already evidenced. Do not infer private DNS, tailnet traversal, authenticated clients or mutation authority from them.
- **D-02:** Prove UUID access and prompt-file write/readback on an actual participating Bot, recording its exact path. A documented path or a value copied from the roster is not a live probe. Preserve existing prompt content and keep credential values out of artifacts; no guessed UUID or manufactured successful write.
- **D-03:** Observe the actual Grok Bot MCP client's `tools/list_changed` behavior, or select and exercise the documented connector fallback on observed non-support. Local server metadata alone is not proof of SaaS client capability. Offline `grok-bot-box`, absent mounted Bot tools and a failed browser relay are bounded access observations, not proof that the separate client is unsupported.
- **D-04:** Obtain actual authenticated Cursor team policy/tier and inventory the remaining prerequisite availability without exposing credential values. If access requires a human, return a blocking human-action checkpoint with the exact missing evidence; do not auto-approve, declare passed or start Phase 2.

### Source and ownership
- **D-05:** Kickoff retains the verbatim ORIGINAL in proposal §1, real traceable Notion Agent Task Graph/Linear Spectrum Web Co node and step links, and those live URLs in the second uplift. Preserve source scope; no fabricated tracker IDs/URLs, tickets, acknowledgements or second-uplift dispatch.
- **D-06:** `.planning/**` is LEAD-owned; `docs/upgrade-plan-desk-v2.md` is QUALITY-owned. Route the §13 source update through the appropriate owning slice and repository protocol. Preserve branch `bot-00-programming-lead/desk-swarm-subagents` and unrelated `web/desk3d/**`; do not silently edit a specialist path as LEAD or rewrite ownership to permit it. Companion agent-substrate has user changes and is not modified in this phase.

### User-resolved choices carried forward
- **D-07:** The user selected weekly Hindsight reflect, VPS plus Mac mini and XPS administrative access with exact mapped-port deny-default grants, and authorized human account-UI skill installation/activation. Seats remain proposal-only while `skills.approve` is absent. Record these now; actual scheduling/ACL/activation evidence belongs to the later phases and is not supplied by the design choice.
- **D-08:** Preserve locked D-1/D-2/D-3 and D-4's original-authoring-session scope. Independent QUALITY approval must bind the exact current reviewed SHA without creating a new tip; do not invent approvals or use on-branch stamp commits as approval. Continue only after actual phase verification; a human deferral is a resumable stop, not dependency clearance.

### Agent discretion
Use existing GSD artifact, ownership and receipt conventions and conservative read-only probes. Technical mechanics may be chosen from source/tool documentation; user decisions or inaccessible runtime evidence may not be guessed. No new capability or scope reduction is authorized.

</decisions>

<canonical_refs>
## Canonical References

Downstream agents MUST read these before planning or implementing; paths are relative to the programming-desk repository root.
- `.planning/PROJECT.md` — fixed milestone scope, locked choices and responsibility boundaries.
- `.planning/REQUIREMENTS.md` — all 16 Phase 1 requirements and primary-phase traceability.
- `.planning/ROADMAP.md` — n1 success criteria and downstream dependency gates.
- `.planning/INGEST-CONFLICTS.md` — the three actual user resolutions and explicit core routing.
- `.planning/intel/constraints.md` — source tool, data, template and protocol invariants.
- `.planning/intel/implementation-map.md` — durable bounded source reconciliation across all seven phases.
- `.planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.md` — parent-observed inventory, attempts and missing evidence.
- `.planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.json` — machine snapshot, actual SSH command supplement and full bounded source reports.
- `docs/upgrade-plan-desk-v2.md` §§1, 5, 7.4, 9.2, 11, 12 kickoff/n1, 13 and Appendix A — approved source and exact assumption checklist.
- `docs/desk-operating-model.md` — production loop, exact-SHA approval, channels and no unsupported skill activation.
- `docs/cross-bot-protocol.md` — actual owned-path routing and contract-first boundaries.
- `docs/quality-gates.md`, `ownership.yaml` — executable gates, ownership and real receipt obligations.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `01-INVENTORY.json` contains the actual five-service listener and node identity evidence; do not repeat it as newly executed work.
- `services/desk-gateway/src/desk_gateway/server.py` defines per-seat and `/mcp/<seat>/packs/<pack>` fallback routes. Source presence is not client acceptance.
- `infra/railway/forwarders.yaml`, `infra/tailscale/desk-acl.hujson` and `infra/desk-gateway/` are existing downstream specifications, not applied networking proof.
- `grokbot/rosters/spectrumwebco.json` and `contracts/tool-rosters/` supply source roster contracts, not actual self-UUID proof or registration.
- `ci/gates/` and `ci/tests/` supply the existing ownership/receipt/security/contract/integrity conventions.

### Established Patterns
Phase plans use `01-NN-PLAN.md`; summaries are written only after actual plan completion. State/roadmap mutations use registered GSD handlers. Checks and commits are parent-owned after disjoint workers land. Live human actions remain blocking checkpoints, regardless of autonomous mode.

### Integration Points
Phase 1 establishes facts for later network/gateway/bootstrap work; it does not paper over their observed failures. The proposal's §13 remains the source assumption record and requires its owning QUALITY slice. Notion/Linear kickoff rows and live Bot/client/account observations require actual connected services or a human action.

</code_context>

<specifics>
## Specific Ideas

User request: “ultrathink orchestrate continue our Phases and push to GitHub.” The user chose initialization from the full Desk v2 plan after no prior GSD milestone was found. Continue the discuss → plan → execute workflow on the existing branch; push verified reachable artifacts, but do not claim the milestone is complete or perform audit/complete/cleanup while a predecessor phase is unverified.

</specifics>

<deferred>
## Deferred Ideas

None — no approved source scope was deferred. Downstream implementation remains assigned to its seven original phases, not discarded.

</deferred>
