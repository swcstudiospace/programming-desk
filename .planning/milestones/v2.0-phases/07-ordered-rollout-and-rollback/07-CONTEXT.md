# Phase 7: Ordered Rollout and Rollback — Context

**Gathered:** 2026-10-08  
**Status:** In Progress / Plan Formulation  
**Mode:** Autonomous orchestration. Governed by `docs/upgrade-plan-desk-v2.md` §12 (n7), `ownership.yaml`, `infra/railway/forwarders.yaml`, `infra/tailscale/policy.hujson`, `infra/substrate/SUBSTRATE-ENV.md`, and REQ-ROLLOUT-001 through REQ-ROLLOUT-013.

<domain>
## Phase Boundary

Phase 7 delivers Workstream G (Ordered rollout and rollback) and source step n7 (`docs/upgrade-plan-desk-v2.md` §12). It consolidates and verifies:
1. **n7.1 Cutover Dependencies (REQ-ROLLOUT-001, REQ-ROLLOUT-012):** Strict execution order: n2 (Network) → n3 (Substrate Data Planes) → n4 (Gateway & Contracts) → n5 (Prompts, Skills, Templates, Plugin) → n6 (Fresh Acceptance & External Intake). Only the n4 gateway skeleton is permitted to start after n1 and overlap n3. Lane C specialist assignments for n2/n5; Lane A Cursor Cloud Agents with second-uplift XML for n3/n4; Lane B only upon explicit Ove request.
2. **n7.2 Rollback Procedures (REQ-ROLLOUT-002..006):** Verifiable, documented rollback plans per node without data loss:
   - Network plane: delete forwarder services, re-create public Greptime domain and Timescale TCP proxy (no data migration involved).
   - Substrate plane: revert `substrate.env` to prior configuration and restart services.
   - Gateway plane: additive removal/disabling of desk-gateway; previous Bot operations continue uninterrupted.
   - Prompts plane: revert v1.1 prompts by re-assembling v1.0 with committed roster; zero hardcoded recipient-breaking IDs.
   - Templates plane: re-publish prior templates in Grok Bot workspace.
3. **n7.3 Operational Coordination (REQ-ROLLOUT-007, REQ-ROLLOUT-008):** Cutover window announcements in Desk channel prior to action; LEAD dispatch notes maintain immutable audit trail.
4. **n7.4 Tracker Synchronization & Ove 1:1 Report (REQ-ROLLOUT-009, REQ-ROLLOUT-010):** Synchronize actual GitHub PR fields (PR #65) to Linear and Notion without inventing merge or deployment state. Complete report to Ove in 1:1 citing all receipt paths and every unverified item.
5. **n7.5 Legacy Node Decommissioning (REQ-ROLLOUT-011):** Retiring legacy `railway-app` (100.77.7.42) only after verified Phase 6 and under recorded Gate G-6 destructive-operation approval.
6. **Final Gate Clearance (REQ-ROLLOUT-013):** Gates G-1 through G-7 verified clean, exact-current-head SHA independent approval, and final milestone verification receipt `.receipts/bot-00-programming-lead/n7-rollout.json`.

Explicitly out of scope:
- Fabricated merge claims or skipping quality gates.
</domain>

<decisions>
## Implementation Decisions

### 1. Strict Cutover Ordering & Dispatch Lanes
- Execution follows the immutable dependency DAG: n2 → n3 → n4 → n5 → n6 → n7.
- Specialists maintain domain boundaries per `ownership.yaml`.

### 2. Verified Rollback Architecture
- Every subsystem retains an explicit, non-destructive rollback path documented in receipts.
- Database volumes remain untouched during forwarder/proxy cutovers.

### 3. Truthful Reporting & Legacy Decommissioning
- Notion and Linear status reflect exact GitHub PR head state.
- `railway-app` decommission requires recorded human approval under G-6.
</decisions>
