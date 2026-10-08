# Roadmap: Programming Desk

## Milestones

- ✅ **v2.1 Live Drills & Intake Hardening** — Phases 8-9 (shipped 2026-10-08)
- ✅ **v2.0 Desk v2** — Phases 1-7 (shipped 2026-10-08) — [Archive](milestones/v2.0-ROADMAP.md)

## Phases

### ✅ v2.1 Live Drills & Intake Hardening (Phases 8-9)

- [x] Phase 8: Gateway Resiliency & Subagent Execution Drills (4/4 plans)
- [x] Phase 9: External Intake Hardening & Telemetry Anchoring (4/4 plans)

### Phase 9: External Intake Hardening & Telemetry Anchoring

**Goal**: Deliver cryptographic webhook verification, schema validation, idempotency deduplication, resilient caching, circuit breaking, DLQ handling, secrets filtering, and OpenTelemetry trace anchoring.
**Requirements**: REQ-INTAKE-001 through REQ-INTAKE-010
**Plans**:
- [x] 09-01-PLAN.md — Webhook HMAC verification, schema validation & sliding idempotency (REQ-INTAKE-001, REQ-INTAKE-003, REQ-INTAKE-004)
- [x] 09-02-PLAN.md — ETag caching, circuit breaker & graceful degradation (REQ-INTAKE-002, REQ-INTAKE-005, REQ-INTAKE-007)
- [x] 09-03-PLAN.md — DLQ retry policies and terminal failure reporting (REQ-INTAKE-008)
- [x] 09-04-PLAN.md — OTel trace propagation, secrets redaction & telemetry anchoring (REQ-INTAKE-006, REQ-INTAKE-009, REQ-INTAKE-010)

### Completed Milestones

<details>
<summary>✅ v2.0 Desk v2 (Phases 1-7) — SHIPPED 2026-10-08</summary>

- [x] Phase 1: Inventory and prove assumptions (7/7 plans)
- [x] Phase 2: Network plane (6/6 plans)
- [x] Phase 3: Substrate data planes (6/6 plans)
- [x] Phase 4: Desk Gateway and contracts (6/6 plans)
- [x] Phase 5: Prompts, skills, templates, plugin (6/6 plans)
- [x] Phase 6: Fresh-desk acceptance and external intake (6/6 plans)
- [x] Phase 7: Ordered rollout and rollback (4/4 plans)

See [milestones/v2.0-ROADMAP.md](milestones/v2.0-ROADMAP.md) for full phase details and execution history.
</details>

## Next Steps

Milestone v2.1 complete! All requirements across Phase 8 (REQ-DRILL-001 through REQ-DRILL-010) and Phase 9 (REQ-INTAKE-001 through REQ-INTAKE-010) have been executed, verified, and merged to main.



[You have received this identical output 3 times. Re-reading '/root/src/repos/programming-desk/.planning/ROADMAP.md:raw' will not change it — use a narrower selector (path:A-B), or proceed with the edit.]

[You have received this identical output 3 times. Re-reading '.planning/ROADMAP.md:raw' will not change it — use a narrower selector (path:A-B), or proceed with the edit.]