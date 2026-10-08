# Phase 7: Ordered Rollout and Rollback — Validation

## Validation Checkpoints

### 1. Cutover Dependency Order (REQ-ROLLOUT-001, REQ-ROLLOUT-012)
- Validate execution traces confirm Phase 2 through Phase 6 completed prior to cutover.
- Confirm lane assignments adhere to rules: n2/n5 Lane C specialist, n3/n4 Lane A Cursor Cloud Agents.

### 2. Per-Node Rollback Procedures (REQ-ROLLOUT-002..006)
- Validate network rollback procedure: forwarder deletion and proxy restoration without data loss.
- Validate substrate rollback procedure: `substrate.env` restoration and service restart.
- Validate gateway rollback: additive service removal leaving seats functional.
- Validate prompt rollback: v1.0 prompt re-assembly avoiding literal IDs.
- Validate template rollback: template re-publication in workspace.

### 3. Operational Announcements and Tracker Sync (REQ-ROLLOUT-007..010)
- Verify cutover window announcements in Desk channel.
- Verify LEAD dispatch notes logged as durable audit trail.
- Confirm Notion and Linear status match actual GitHub PR #65 fields.
- Validate 1:1 report to Ove citing all receipt paths and honest `unverified` entries.

### 4. Legacy Node Decommissioning (REQ-ROLLOUT-011)
- Verify `railway-app` is decommissioned only after Phase 6 acceptance is verified.
- Confirm Gate G-6 destructive-operation approval compliance with all required fields.

### 5. Final Release & Gate Clearance (REQ-ROLLOUT-013)
- Verify Gates G-1 through G-7 pass cleanly.
- Validate exact-current-head SHA independent approval on receipt `.receipts/bot-00-programming-lead/n7-rollout.json`.
