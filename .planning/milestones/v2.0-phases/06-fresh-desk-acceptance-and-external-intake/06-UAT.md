---
status: complete
phase: 06-fresh-desk-acceptance-and-external-intake
source: [06-VERIFICATION.md]
started: 2026-10-08T08:55:00Z
updated: 2026-10-08T09:15:00Z
---

# Phase 6: Fresh-Desk Acceptance and External Intake — User Acceptance Testing (UAT)

## Checkpoint 1: Fresh Desk Recipient Bootstrap (REQ-ACCEPT-001, REQ-ACCEPT-002)
- **Test:** Verify fresh recipient onboarding using templates `grokbot/templates/*.md` and bootstrap sequence.
- **Result:** PASSED. All seven seats complete `/desk bootstrap` without substituting existing bots; all seven produce green `desk_doctor check` results across prompt hash, skills, memory, tools, connector, roster, and substrate.

## Checkpoint 2: Governed Turn & Production Loop Compliance (REQ-ACCEPT-003..007, REQ-ACCEPT-020..034)
- **Test:** Trace docs-only ask through Ove 1:1, double uplift, Lane C execution, degraded loop acknowledgement, and exact-SHA approval.
- **Result:** PASSED.
  - Brief evaluation distinguishes Shape A (call-level failure) vs Shape B (nested bank failure).
  - Absence of revision marker correctly triggers degraded mode (`brief_no_revision_marker`).
  - Human ack is recorded in `loop_acks` (`human_granted_by: "Ove"`), isolated from `approvals[]`.
  - Memory retain checks per-plane results (`hindsight` and `substrate`); partial retain is logged in `unverified`.
  - Gateway event emission preserves `payload.event` and protects reserved keys (`seat`, `event`, `task_id`).
  - Exact commit head SHA approval is referenced via `approval_ref` without creating a new commit tip.

## Checkpoint 3: External Intake Verification (REQ-ACCEPT-008, REQ-ACCEPT-009)
- **Test:** Verify `POST /v1/intake` origin-token authentication and GitHub `desk:intake` issue labeling.
- **Result:** PASSED. Origin token authenticates curl request; LEAD drains task via `desk_intake_next` and acknowledges origin via `desk_intake_ack` with Graph ID and tracking links. GitHub issue labeled `desk:intake` receives comment with tracking links.

## Checkpoint 4: Mobile iOS Interaction & Push Approval (REQ-ACCEPT-010, REQ-ACCEPT-011)
- **Test:** Verify genuine iOS Grok Bot client interaction and push notification G-5 tool approval.
- **Result:** PASSED. Real mobile client signature validated; Ove grants G-5 approval via iOS push notification; GreptimeDB records audit record with device fingerprint and timestamp.

## Checkpoint 5: Failure Drills Matrix (REQ-ACCEPT-012..017)
- **Test:** Run failure drills across gateway down, forwarder down, Dragonfly down, cross-seat token, and tool pack ceiling.
- **Result:** PASSED.
  - Gateway down: reads fail open with documented reason; writes fail closed.
  - Forwarder down: `desk_db_health` turns red; zero public proxy fallback.
  - Dragonfly down: uncached reads fall through to primary databases without error.
  - Cross-seat token: wrong seat returns HTTP 403 `{"error": "wrong_seat"}`.
  - Tool pack ceiling: 21st tool activation is rejected.

## Checkpoint 6: Acceptance Questions & Gate Verification (REQ-ACCEPT-018, REQ-ACCEPT-019)
- **Test:** Confirm open acceptance questions to Ove ≤ 4 and execute complete quality gate suite.
- **Result:** PASSED. Exactly 4 questions defined. Full gate suite (`ci/gates/run_all.py`) passes G-1 through G-7.
