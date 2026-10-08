# Roadmap: Programming Desk

## Milestones

- 🟡 **v2.4 Multi-Region Edge Federation & Autonomous Chaos Recovery** — Phases 14-15 (in progress)
- ✅ **v2.3 Production Cutover, Dynamic Failover & Telemetry Alerting** — Phases 12-13 (shipped 2026-10-09) — [Archive](milestones/v2.3-ROADMAP.md)
- ✅ **v2.2 Multi-Desk Federation & Staging Deployments** — Phases 10-11 (shipped 2026-10-09) — [Archive](milestones/v2.2-ROADMAP.md)
- ✅ **v2.1 Live Drills & Intake Hardening** — Phases 8-9 (shipped 2026-10-08) — [Archive](milestones/v2.1-ROADMAP.md)
- ✅ **v2.0 Desk v2** — Phases 1-7 (shipped 2026-10-08) — [Archive](milestones/v2.0-ROADMAP.md)

## Phases

### 🟡 v2.4 Multi-Region Edge Federation & Autonomous Chaos Recovery (Phases 14-15)

- [x] Phase 14: Multi-Region Edge Federation & WAN Routing (2/2 plans)
- [ ] Phase 15: Autonomous Chaos Recovery & Self-Healing Resilience (0/2 plans)

#### Phase 14: Multi-Region Edge Federation & WAN Routing

**Goal**: Deliver multi-region edge ingress routing, distributed rate limiting, cross-region WAN inter-seat routing, and high-latency vector clock convergence.
**Requirements**: REQ-EDGE-001 through REQ-EDGE-005
**Plans**:
- [x] 14-01-PLAN.md — Multi-region edge ingress gateway, geo-steering & distributed rate limiting (REQ-EDGE-001, REQ-EDGE-002)
- [x] 14-02-PLAN.md — Cross-region WAN inter-seat routing, cryptographic attestation & high-latency vector clock convergence (REQ-EDGE-003, REQ-EDGE-004, REQ-EDGE-005)

#### Phase 15: Autonomous Chaos Recovery & Self-Healing Resilience

**Goal**: Implement synthetic chaos injection, automated self-healing seat reconstitution, workload rebalancing, and DLQ replay orchestrator.
**Requirements**: REQ-CHAOS-001 through REQ-CHAOS-005
**Plans**:
- [ ] 15-01-PLAN.md — Synthetic chaos injection harness & automated self-healing supervisor (REQ-CHAOS-001, REQ-CHAOS-002)
- [ ] 15-02-PLAN.md — Autonomous workload rebalancing, DLQ replay orchestrator & resilience verification suite (REQ-CHAOS-003, REQ-CHAOS-004, REQ-CHAOS-005)

### Completed Milestones

<details>
<summary>✅ v2.3 Production Cutover, Dynamic Failover & Telemetry Alerting (Phases 12-13) — SHIPPED 2026-10-09</summary>

- [x] Phase 12: Production Cutover & Dynamic Failover (2/2 plans)
- [x] Phase 13: Advanced Telemetry, SLOs & Alert Thresholds (2/2 plans)

See [milestones/v2.3-ROADMAP.md](milestones/v2.3-ROADMAP.md) for full phase details and execution history.
</details>

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
