# Roadmap: Programming Desk

## Milestones

- 🟡 **v2.3 Production Cutover, Dynamic Failover & Telemetry Alerting** — Phases 12-13 (in progress)
- ✅ **v2.2 Multi-Desk Federation & Staging Deployments** — Phases 10-11 (shipped 2026-10-09) — [Archive](milestones/v2.2-ROADMAP.md)
- ✅ **v2.1 Live Drills & Intake Hardening** — Phases 8-9 (shipped 2026-10-08) — [Archive](milestones/v2.1-ROADMAP.md)
- ✅ **v2.0 Desk v2** — Phases 1-7 (shipped 2026-10-08) — [Archive](milestones/v2.0-ROADMAP.md)

## Phases

### 🟡 v2.3 Production Cutover, Dynamic Failover & Telemetry Alerting (Phases 12-13)

- [x] Phase 12: Production Cutover & Dynamic Failover (2/2 plans)
- [ ] Phase 13: Advanced Telemetry, SLOs & Alert Thresholds (1/2 plans)

#### Phase 12: Production Cutover & Dynamic Failover

**Goal**: Deliver live traffic migration with zero request loss, automated multi-desk failover routing, upstream health polling, and canary traffic splitting.
**Requirements**: REQ-CUTOVER-001 through REQ-CUTOVER-005
**Plans**:
- [x] 12-01-PLAN.md — Production live cutover orchestrator, canary traffic splitting & emergency rollback (REQ-CUTOVER-001, REQ-CUTOVER-004, REQ-CUTOVER-005)
- [x] 12-02-PLAN.md — Dynamic multi-desk failover routing & upstream health polling (REQ-CUTOVER-002, REQ-CUTOVER-003)

#### Phase 13: Advanced Telemetry, SLOs & Alert Thresholds

**Goal**: Implement Prometheus per-seat SLO metrics export, automated alert threshold dispatch, Solana devnet anchor verification, and telemetry audit suites.
**Requirements**: REQ-ALERT-001 through REQ-ALERT-005
**Plans**:
- [x] 13-01-PLAN.md — Prometheus SLO metrics export, alert threshold dispatcher & on-call webhook notification (REQ-ALERT-001, REQ-ALERT-002, REQ-ALERT-003)
- [ ] 13-02-PLAN.md — Solana devnet anchor verification & synthetic telemetry stress test suite (REQ-ALERT-004, REQ-ALERT-005)

### Completed Milestones

<details>
<summary>✅ v2.2 Multi-Desk Federation & Staging Deployments (Phases 10-11) — SHIPPED 2026-10-09</summary>

- [x] Phase 10: Multi-Desk Federation & Inter-Seat Routing (2/2 plans)
- [x] Phase 11: Automated Staging & VPS Environment Promotion (2/2 plans)

See [milestones/v2.2-ROADMAP.md](milestones/v2.2-ROADMAP.md) for full phase details and execution history.
</details>

<details>
<summary>✅ v2.1 Live Drills & Intake Hardening (Phases 8-9) — SHIPPED 2026-10-08</summary>

- [x] Phase 8: Gateway Resiliency & Subagent Execution Drills (4/4 plans)
- [x] Phase 9: External Intake Hardening & Telemetry Anchoring (4/4 plans)

See [milestones/v2.1-ROADMAP.md](milestones/v2.1-ROADMAP.md) for full phase details and execution history.
</details>

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
