# Phase 6: Fresh-Desk Acceptance and External Intake — Patterns

## Pattern 1: Production Loop Execution Trace
A production turn follows the strict five-phase sequence:
```
Turn Start
  │
  ├─ Phase 1: memory_brief / desk_brief
  │    ├─ Check Shape A (top-level error/reason) ──▶ Stop & report degraded turn
  │    ├─ Check Shape B (substrate.error, recall.error, recall.results[i].error) ──▶ Stop & report degraded turn
  │    └─ Check Revision Marker (etag)
  │         └─ Absent (desk_brief today) ──▶ Request degraded ack (brief_no_revision_marker)
  │
  ├─ Degraded Turn Acknowledgement
  │    └─ Recorded in loop_acks: {condition, operation, ack_id, human_granted_by: "Ove", at, scope}
  │
  ├─ Phase 2: Act (Edit code within owned paths per ownership.yaml)
  │
  ├─ Phase 3: memory_write / desk_memory_retain
  │    ├─ Check results.hindsight and results.substrate
  │    └─ If partial, document in unverified; do not round up to full retain
  │
  ├─ Phase 4: events_emit / desk_event_emit
  │    └─ Payload carries {event: "<kind>", receipt_path, degraded: true, blocker, ack, ...}
  │
  └─ Turn Complete (Post "awaiting-review / pending QUALITY" in Desk channel)
```

## Pattern 2: Exact-SHA Quality Approval Reference
To avoid creating a new commit tip that invalidates the approval, receipts reference an external approval surface:
```json
{
  "schema_version": 1,
  "task_id": "lane-c-docs-example",
  "bot": "bot-01-systems-backend",
  "branch": "bot-00-programming-lead/desk-swarm-subagents",
  "approval_ref": {
    "kind": "check_run",
    "name": "desk/quality-approval",
    "reviewed_sha": "0bfcdec6d92ec0f4ae8b7636e6b52c00d4aa697d",
    "resolved_by": "G-2 at gate time"
  },
  "approved_by": "SomeRandmGuyy",
  "commands": [...],
  "claims": [...],
  "unverified": [...]
}
```

## Pattern 3: Origin Intake and Acknowledgment
External systems submit work through the authenticated intake gateway:
```bash
curl -X POST https://desk.swcstudio.space/v1/intake \
  -H "Authorization: Bearer $INTAKE_ORIGIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "customer-support-webhook",
    "title": "Bug in Edge Routing",
    "description": "Details...",
    "priority": "high"
  }'
```
LEAD acknowledges back:
```json
{
  "status": "acknowledged",
  "intake_id": "intake-9823",
  "graph_id": "ut-desk-v2",
  "linear_issue": "SPE-5021",
  "notion_page": "https://notion.so/..."
}
```

## Pattern 4: Failure Drill Verification Matrix
```
| Scenario | Trigger / Injection | Expected Outcome | Verified Mechanism |
|---|---|---|---|
| Gateway Down | Stop desk-gateway service | Reads fail open (unknown returned), Writes fail closed | Local fallback handling |
| Forwarder Down | Stop tailscale forwarder | desk_db_health = RED, no public proxy fallback | Tailnet isolation |
| Cache Down | Stop Dragonfly container | Uncached data returned from Timescale/Greptime | Read pass-through |
| Wrong Seat | Seat Web uses token on /mcp/ios | HTTP 403 {"error": "wrong_seat"} | Gateway seat claims check |
| Pack Ceiling | Activate 6th tool pack item | Refusal: live tools exceeds 20 | Gateway ceiling enforcement |
```
