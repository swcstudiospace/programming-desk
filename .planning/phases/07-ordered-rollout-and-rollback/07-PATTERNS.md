# Phase 7: Ordered Rollout and Rollback — Patterns

## Pattern 1: Dependency Order and Verification Gate
```
Phase 1: Inventory & Assumptions (n1) ──▶ PASS
  │
Phase 2: Network Plane (n2) ──▶ PASS
  │
Phase 3: Substrate Data Planes (n3) ──▶ PASS
  │
Phase 4: Desk Gateway & Contracts (n4) ──▶ PASS
  │
Phase 5: Prompts, Skills, Templates, Plugin (n5) ──▶ PASS
  │
Phase 6: Fresh Acceptance & External Intake (n6) ──▶ PASS
  │
Phase 7: Cutover, Decommissioning & Sync (n7) ──▶ Clearance
```

## Pattern 2: G-6 Approved Decommissioning Pattern
For decommissioning legacy nodes (e.g. `railway-app`):
```json
{
  "commands": [
    {
      "cmd": "railway service delete --service railway-app --project ultrathink",
      "exit_code": 0,
      "duration_s": 2.1,
      "output_tail": "Service railway-app deleted"
    }
  ],
  "approvals": [
    {
      "operation": "decommission legacy railway-app subnet router node (100.77.7.42)",
      "approved_by": "SomeRandmGuyy",
      "at": "2026-10-08T09:20:00Z",
      "blast_radius": "Railway project ultrathink legacy subnet router; superseded by private forwarders"
    }
  ],
  "rollback_plan": "Re-deploy railway-app template with CIDR 10.0.0.0/16 router configuration"
}
```

## Pattern 3: Rollout Dispatch and Coordination
- Desk Announcement:
  `[LEAD] Cutover Window Starting: Re-routing database connections to Tailscale forwarders. Rollback plan: restore substrate.env.bak.`
- Event Emission:
  `desk_event_emit(kind="implementation.completed", payload={"task_id": "n7-rollout", "step": "cutover"})`
