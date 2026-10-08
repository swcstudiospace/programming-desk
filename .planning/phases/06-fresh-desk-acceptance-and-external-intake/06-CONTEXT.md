# Phase 6: Fresh-Desk Acceptance and External Intake — Context

**Gathered:** 2026-10-08  
**Status:** In Progress / Plan Formulation  
**Mode:** Autonomous orchestration. Governed by `docs/upgrade-plan-desk-v2.md` §9.4, §10, §12 (n6), `ownership.yaml`, `skills/desk-bootstrap/desk-production-loop/SKILL.md`, and REQ-ACCEPT-001 through REQ-ACCEPT-034.

<domain>
## Phase Boundary

Phase 6 delivers Workstream F (Fresh-desk acceptance and external intake) and source step n6 (`docs/upgrade-plan-desk-v2.md` §9.4, §12). It validates:
1. **n6.1 Fresh-Recipient Verification:** A user who has never had the desk adds the seven templates (`grokbot/templates/*.md`), executes `/desk bootstrap`, and achieves 7 green `desk_doctor check` results across all 7 seats without substituting existing bots or synthetic bypasses.
2. **n6.2 Governed Production Turn & Docs-Only Uplift:** A docs-only request entering via Ove 1:1 to LEAD executes the double uplift, produces one concrete Lane C ticket for its owning seat, emits `implementation.completed` with `awaiting-review / pending QUALITY`, and resolves an exact-current-SHA independent approval without creating a new commit tip. Enforces production loop governance:
   - Brief evaluation: Shape A (call-level refusal with top-level error/reason) vs Shape B (completed brief with buried nested error in `substrate.error` or `recall.results[].error`).
   - Revision marker handling: absence of `brief_etag` in `desk_brief` requires human degraded-turn acknowledgement (`brief_no_revision_marker` or `brief_degraded`) recorded under `loop_acks` (never `approvals[]`).
   - Memory retain: non-atomic per-plane checks (`results.hindsight` vs `results.substrate`), unverified recording for partial retention, recall preceding single retry.
   - Event emission: gateway fixed envelope (`kind: "note"`, routing via `payload.event`), reservation of `seat`, `event`, `task_id`.
   - Handoff packets: unsigned status in unverified pending SPE-4792.
3. **n6.3 External Intake Pipelines:** Validation of `POST /v1/intake` origin-token authentication with LEAD `desk_intake_next` draining and acknowledgment back to origin, plus GitHub issue `desk:intake` workflow with Graph ID and tracker links.
4. **n6.4 Mobile & G-5 Push Notification Approval:** Real iOS interaction between Ove and LEAD, plus push notification G-5 gated tool approval recorded with genuine cryptographic/audit evidence without synthetic authorization.
5. **n6.5 Failure Drills:**
   - Gateway down: read tools fail-open with documented reason; write tools fail-closed without claims.
   - Forwarder outage: `desk_db_health` turns red, absolutely zero public domain or proxy fallback.
   - Dragonfly down: fall-through to uncached substrate data retrieval.
   - Cross-seat token isolation: wrong-seat token invocation returns HTTP 403 `{"error": "wrong_seat"}`.
   - Tool pack ceiling: activation of a 21st tool is rejected.
6. **n6.6 Acceptance Questions & Closure:** Strict cap of at most four open acceptance questions to Ove. Quality Gate verification across G-1 through G-7, culminating in `.receipts/bot-00-programming-lead/n6-accept.json`.

Explicitly out of scope for Phase 6:
- Decommissioning of legacy infrastructure (`railway-app` retirement under Gate G-6, scheduled for Phase 7).
- Final PR merge into main and tag cutover (Phase 7).

</domain>

<decisions>
## Implementation Decisions

### 1. Fresh-Desk Bootstrap Integrity (REQ-ACCEPT-001, REQ-ACCEPT-002)
- Existing production bots cannot substitute for fresh recipients.
- Seven templates under `grokbot/templates/*.md` must be instantiated in a clean environment, verifying each step: OAuth authentication, UUID/channel registration, group configuration, prompt hashing, and doctor verification.
- Live doctor output must evidence all 7 subsystems (prompt, skills, memory, tools, connector, roster, substrate) green.

### 2. Governed Production Loop & Independent Approval (REQ-ACCEPT-003..007, REQ-ACCEPT-020..034)
- **Brief Precondition & Degraded Mode:** Repo work requires a successful brief AND a revision marker. In current `desk_brief`, no etag is emitted, so every editing turn operates in degraded mode (`brief_no_revision_marker`) requiring human acknowledgement in `loop_acks` before edits.
- **Loop Acks Isolation:** `loop_acks` entries must contain `condition`, `operation`, `ack_id`, `human_granted_by`, `at`, and `scope`. Under zero circumstances can a turn ack be placed in `approvals[]` (which G-6 pairs by count to destructive operations).
- **Exact-SHA Approval:** Quality approval is bound to an exact commit SHA and must not create a new tip. The receipt points to an external approval surface (`approval_ref`), preserving the reviewed commit head.

### 3. Intake & Mobile Evidence (REQ-ACCEPT-008..011)
- Curl origin token intake reaches LEAD intake queue and acknowledges origin.
- GitHub `desk:intake` issue labeling triggers ingestion, emitting issue comments with Graph ID links.
- iOS mobile interaction and push-notification approval must be proven with genuine audit trails.

### 4. Failure Resilience (REQ-ACCEPT-012..017)
- Gateway down: read fail-open returns unknown, never fabricates facts; write fail-closed halts mutation.
- Tailscale forwarder down: `desk_db_health` reports red; traffic never falls back to public proxies.
- Dragonfly down: cache misses bypass smoothly to primary databases without crashing.
- Wrong seat: HTTP 403 forbidden cleanly enforced.
- Tool ceiling: 20 live tools enforced; 21st tool rejected.

### 5. Operator Questions & Gate Clearance (REQ-ACCEPT-018, REQ-ACCEPT-019)
- Open acceptance questions presented to Ove must not exceed four.
- Clearance is granted solely by independent QUALITY verification and validated receipts under Gate G-2.
</decisions>
