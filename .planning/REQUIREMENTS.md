# Requirements: Milestone v2.4 — Multi-Region Edge Federation & Autonomous Chaos Recovery

This document defines the requirements for Milestone v2.4 of Programming Desk.

## 1. Multi-Region Edge Federation & WAN Inter-Seat Routing (Phase 14)

- [x] **REQ-EDGE-001**: Edge ingress gateway proxying and load balancing across multi-region VPS desk instances with latency-based geo-steering and health-aware failover.
- [x] **REQ-EDGE-002**: Distributed edge rate limiting and token-bucket traffic policing synchronized via DragonflyDB cache cluster with per-seat burst ceilings.
- [ ] **REQ-EDGE-003**: Cross-region WAN inter-seat routing protocol enforcing cryptographic seat identity attestation and mutual TLS over Tailnet mesh.
- **REQ-EDGE-004**: Vector clock conflict convergence with multi-master partitioned task graphs under high-latency WAN transit (>250ms).
- **REQ-EDGE-005**: Dynamic edge route revocation and instantaneous session evacuation upon region-wide impairment detection.

## 2. Autonomous Chaos Recovery & Self-Healing Resilience (Phase 15)

- **REQ-CHAOS-001**: Synthetic chaos injection harness simulating intermittent upstream network partitions, packet loss, and latency spikes across Railway dependencies.
- **REQ-CHAOS-002**: Automated self-healing supervisor detecting corrupted or partitioned seat instances and triggering zero-downtime hot reconstitution.
- **REQ-CHAOS-003**: Autonomous task graph rebalancing algorithm dynamically redistributing unacknowledged seat workloads upon seat crash or unresponsiveness.
- **REQ-CHAOS-004**: Automated dead-letter queue (DLQ) replay orchestrator with exponential backoff, jitter, and poisonous payload quarantine.
- **REQ-CHAOS-005**: Continuous resilience verification suite validating system-wide RPO (Recovery Point Objective = 0) and RTO (Recovery Time Objective < 3s) during chaos drills.
