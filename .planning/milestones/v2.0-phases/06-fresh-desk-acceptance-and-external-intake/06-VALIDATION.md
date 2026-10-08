# Phase 6: Fresh-Desk Acceptance and External Intake — Validation

## Validation Checkpoints

### 1. Fresh Bootstrap Verification (REQ-ACCEPT-001, REQ-ACCEPT-002)
- Validate 7-seat template structure against bootstrap specifications.
- Verify that fresh bootstrap procedure produces 7 green `desk_doctor check` results across prompt hash, skills, memory, tools, connector, roster, and substrate.

### 2. Governed Ticket Turn & Exact-SHA Approval (REQ-ACCEPT-003..007, REQ-ACCEPT-020..034)
- Validate production loop execution traces:
  - Detection of Shape A vs Shape B brief failures.
  - Absence of revision marker requiring degraded turn ack in `loop_acks`.
  - Non-pollution of `approvals[]` with turn acks.
  - Partial memory retention recorded in `unverified`.
  - Event emission preserving `payload.event` and protecting reserved keys (`seat`, `event`, `task_id`).
- Verify exact-SHA approval pointer (`approval_ref`) resolving without advancing branch commit tip.

### 3. Intake Ingestion & Acknowledgment (REQ-ACCEPT-008, REQ-ACCEPT-009)
- Test curl origin token ingestion on `POST /v1/intake`.
- Verify LEAD draining via `desk_intake_next` and dispatching acknowledgments with Graph ID and tracker links.
- Verify GitHub `desk:intake` issue labeling workflow.

### 4. Mobile iOS Approval Evidence (REQ-ACCEPT-010, REQ-ACCEPT-011)
- Verify mobile interaction evidence between Ove and LEAD.
- Validate push notification gated G-5 tool approval flow with genuine audit parameters.

### 5. Failure Drills Verification (REQ-ACCEPT-012..017)
- Gateway down: reads fail open, writes fail closed.
- Forwarder down: `desk_db_health` is red; zero public proxy fallback.
- Cache down: fallback to direct data retrieval without crashes.
- Wrong seat: HTTP 403 `{"error": "wrong_seat"}`.
- Pack ceiling: 21st tool rejected.

### 6. Acceptance Questions & Gate Clearance (REQ-ACCEPT-018, REQ-ACCEPT-019)
- Confirm open questions to Ove <= 4.
- Verify independent QUALITY approval and validate Gate G-2 receipt.
