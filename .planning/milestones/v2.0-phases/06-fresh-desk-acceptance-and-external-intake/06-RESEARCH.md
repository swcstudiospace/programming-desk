# Phase 6: Fresh-Desk Acceptance and External Intake — Research & Findings

**Gathered:** 2026-10-08  
**Scope:** REQ-ACCEPT-001 through REQ-ACCEPT-034

## 1. Production Loop Discipline (`desk-production-loop`)
The production loop establishes strict invariants for turn execution:
1. **Precondition (Brief + Revision Marker):** Repo work requires a successful brief AND a revision marker.
2. **Two Brief Failure Shapes:**
   - **Shape A (Call-level failure):** Sparse JSON containing top-level `error` and `reason` (`unknown_tool`, `deadline`, `forbidden`, `invalid_args`, `secret_refused`, `backend_missing`, `internal`). Top-level reason is quoted; no nested fields exist.
   - **Shape B (Completed brief failure):** Full brief returned, but contains nested errors in `substrate.error`, `recall.error`, or any `recall.results[i].error`. Even if a single bank (`pd-desk`) fails, the entire brief is failed.
3. **Absence of Revision Marker:**
   - Today's `desk_brief` contract lacks `etag` output. `generated_at` and `cached` do NOT substitute for an etag.
   - A turn editing repo files must record human acknowledgement under `loop_acks` with condition `brief_no_revision_marker` and operation `degraded-loop: repo work on a brief with no revision marker`.
4. **Loop Acks Invariant:**
   - Structure: `{"condition", "operation", "ack_id", "human_granted_by", "at", "scope"}`.
   - `human_granted_by` must be a human name (e.g. `Ove`), NEVER a bot ID or seat name (`bot-00-programming-lead`, `LEAD`).
   - Must never be placed in `approvals[]` (which G-6 pairs by count against destructive operations).
5. **Memory Retain Discipline:**
   - Multi-plane write (`hindsight` and `substrate`). `ok: true` means `any()`.
   - If one plane fails, it is a partial write recorded in `unverified`.
   - Retries must be preceded by recall, and capped at 1 retry with potential duplicate disclosure.
6. **Event Emission Discipline:**
   - Gateway envelope sets top-level `kind: "note"`.
   - Event routing is preserved in `payload.event` and `summary`.
   - Gateway automatically injects `seat`, `event`, and `task_id`; caller must never overwrite these keys in `payload`.
   - Degradation is signalled in payload (`degraded: true`, `blocker`, `upstream_reason`, `reason_path`, `ack`), never by replacing event kind with `ticket.blocked` if work completed.

## 2. Fresh-Desk Acceptance Architecture (n6.1)
- Fresh recipient receives 7 templates from `grokbot/templates/*.md`.
- Bootstrap sequence:
  1. Desktop OAuth login to public gateway (`https://desk.swcstudio.space`).
  2. Register UUID and channel.
  3. Form 6-seat channel group (LEAD in, QUALITY off-channel).
  4. Write pinned prompt XML and verify hash.
  5. Hold routines paused.
  6. Seed memory banks.
  7. Execute `desk_doctor check` across all 7 seats until 100% green.

## 3. Docs-Only Uplift & Exact-SHA Approval (n6.2)
- Ove 1:1 message to LEAD enters ticket.
- Double uplift: first uplift produces Graph of Thought, second uplift links live tracking tickets in Linear and Notion.
- Lane C ticket dispatched to owning seat.
- Seat finishes work, creates verification receipt, posts `awaiting-review / pending QUALITY`.
- Independent QUALITY review approves the exact commit head SHA without committing to the branch (using `approval_ref` pointer to GitHub check run, PR review, or external store record).

## 4. External Intake Flow (n6.3)
- `POST https://desk.swcstudio.space/v1/intake`:
  - Requires Bearer token matching `DESK_INTAKE_ORIGIN_TOKENS`.
  - Enqueues task payload in TimescaleDB `desk_intake` table.
  - LEAD invokes `desk_intake_next` to dequeue.
  - LEAD invokes `desk_intake_ack` with Graph ID and tracker links to notify origin.
- GitHub `desk:intake` label:
  - Workflow webhook or 10-minute polling picks up labeled issue.
  - LEAD comments on issue with tracking details.

## 5. Mobile & G-5 Push Approvals (n6.4)
- Ove interacts with LEAD via Grok Bot iOS application.
- G-5 destructive or high-risk operation generates mobile push notification.
- Ove grants approval from iOS device.
- Audit entry in GreptimeDB records approval ID, timestamp, and device fingerprint.

## 6. Failure Drills Matrix (n6.5)
1. **Gateway Down:** Reads fail open returning unknown/unreachable reason; writes fail closed (refusing state changes).
2. **Forwarder Down:** `desk_db_health` returns red; no fallback to public database endpoints.
3. **Dragonfly Down:** Gateway falls back to direct database reads without cache.
4. **Wrong Seat:** Token with seat claim X calling endpoint `/mcp/Y` returns HTTP 403 `{"error": "wrong_seat"}`.
5. **Pack Ceiling:** Adding a 6th pack tool to a seat already holding 15 core/seat tools + 5 pack tools triggers tool limit refusal (max 20).

## 7. Acceptance Questions Constraint (n6.6)
- Exactly ≤ 4 open acceptance questions can be presented to Ove.
