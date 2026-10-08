# Requirements: Milestone v2.5 — Multi-Tenant Governance & Inter-Desk Agent Mesh

This document defines the requirements for Milestone v2.5 of Programming Desk.

## 1. Multi-Tenant Governance & RBAC Policy Enforcement (Phase 16)

- [x] **REQ-TENANT-001**: Multi-tenant isolation engine enforcing organization and team namespaces across all gateway endpoints, preventing cross-tenant data leakage.
- [x] **REQ-TENANT-002**: Attribute-based & role-based access control (ABAC/RBAC) policy engine governing per-seat tool invocation privileges and data-plane access.
- [ ] **REQ-TENANT-003**: Tenant-scoped Hindsight memory partitions and RAGFlow document dataset isolation with cryptographically authenticated tenant boundaries.
- [ ] **REQ-TENANT-004**: Multi-tenant quota and rate limiting policer with tenant-level burst ceilings and fair-share scheduling.
- [ ] **REQ-TENANT-005**: Tenant audit trail verification with immutable per-tenant cryptographic event hashing and tamper detection.

## 2. Inter-Desk Agent Mesh & Distributed Work Distribution (Phase 17)

- [ ] **REQ-MESH-001**: Inter-desk agent service discovery protocol registering autonomous desk instances (Programming, Recruitment, Trading) over Tailnet mesh.
- [ ] **REQ-MESH-002**: Asynchronous inter-desk RPC protocol via VPS Agent Bus enabling cross-desk task handoffs and progress tracking.
- [ ] **REQ-MESH-003**: Cross-organization receipt co-signing protocol verifying multi-agent task completion with dual-party cryptographic attestation.
- [ ] **REQ-MESH-004**: Decentralized task delegation state machine handling timeout negotiation, delegation rejection, and automated recall to originating desk.
- [ ] **REQ-MESH-005**: Continuous inter-desk mesh verification test suite validating end-to-end multi-desk ticket lifecycle and receipt reconciliation.

