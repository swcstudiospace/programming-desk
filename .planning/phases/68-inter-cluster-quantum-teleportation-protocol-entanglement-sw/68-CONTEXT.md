# Phase 68: Inter-Cluster Quantum Teleportation Protocol & Entanglement Swarm Routing — Context

**Gathered:** 2026-10-09
**Status:** Ready for planning; acceptance reopened by the milestone audit
**Source:** Autonomous milestone execution; explicit user decision in this conversation

<domain>
## Phase Boundary

Implement and verify REQ-QTELEPORT-001–005 without weakening their numerical or resource-lifecycle criteria. Bell distribution, genuine repeater BSM, three-qubit teleportation with F >= 0.95, probabilistic bilateral purification, and the specified REST route families are required. This is a repair of the audited implementation, not a new milestone.
</domain>

<decisions>
## Implementation Decisions

### Execution model
- **D-68-01 — User selected “Faithful distributed simulator”.** Numerically validated joint-state evolution, explicit node ownership, and classical transport are required. Metadata-only Bell labels and direct amplitude copying are unacceptable. Physical quantum-hardware or quantum-security claims are excluded.
- Exercise separate simulator-node processes, not merely a single object with different node labels. A central joint-state simulator may retain correlations while remote node workers own allocations and apply received classical corrections. No cloning of the input amplitudes as the receiver reconstruction.
- Use the existing Python gateway and existing public phase symbols where they remain meaningful. Cut over every affected caller; no deprecated aliases or re-export shims.

### Acceptance and repository boundaries
- F >= 0.95 is the teleport success predicate. Consumption is single-use; invalid endpoints, repeated inputs, consumed resources, invalid amplitudes and exhausted capacities cannot yield green outcomes.
- Purification must model actual bilateral gates and measurement branches, including parity-rejection consumption. Routing must track physical-model fidelity, allocations and releases; it must not reuse a discarded pair on failure.
- Explicitly distinguish ideal state-vector results from noisy density-matrix results and from remote-process transport evidence.
- Work only on isolated feature worktrees and draft PRs. Independent review remains a blocker; no merge, auto-merge, force-push, branch deletion or milestone archive is authorized by these choices.

### Builder discretion
- Numerical representation, gate kernels, deterministic test RNG injection, node transport implementation, and precise validated request shapes: choose the smallest maintainable design satisfying the original criteria and existing gateway patterns.
</decisions>

<canonical_refs>
## Canonical References
- `.planning/REQUIREMENTS.md` — unchanged original REQ-QTELEPORT-001–005.
- `.planning/ROADMAP.md` — phase boundary.
- `.planning/v5.1-MILESTONE-AUDIT.md` — observed implementation gaps and closure conditions.
- `services/desk-gateway/src/desk_gateway/quantum_teleportation.py` — current lifecycle and invalid amplitude-copy implementation.
- `services/desk-gateway/src/desk_gateway/server.py` — current phase 68 routes, lines 6255–6354 at main 2229570.
- `services/desk-gateway/src/desk_gateway/config.py` — environment-backed settings and seat-passphrase authorization.
- `services/desk-gateway/README.md` — runtime and test conventions.
- `ownership.yaml`, `docs/cross-bot-protocol.md`, `skills/verification-receipts/SKILL.md` — ownership, contract and evidence requirements.
</canonical_refs>

<code_context>
## Existing Code Insights
- Keep `BellPairPool`, `EntanglementPurifier`, `EntanglementSwapper`, `QuantumRepeaterMesh`, and `QuantumTeleportationProtocol` rather than a parallel convention.
- Python 3.11+; httpx, Starlette/MCP and uvicorn already installed by the locked gateway environment.
- Gateway settings already resolve authenticated seats. Simulator-node endpoint addresses must be operator-configured, not arbitrary URLs from requests.
- Product implementation worktree: `/tmp/desk-v51-implementation`, branch `bot-01-systems-backend/v5.1-faithful-simulator`, fork main 2229570. Planning artifacts remain in this LEAD-owned audit worktree; do not mutate the user's root checkout.
- Phase 69 consumes numerical state operations, node transport, pool lifecycle events and teleport proof data. Resolve that shared contract before independent execution slices start.
</code_context>

<specifics>
## Specific Ideas
The user approved a faithful distributed simulator. A deterministic local model is not evidence of physical security; the runtime drill must state its model and exercise real process transport.
</specifics>

<deferred>
## Deferred Ideas
None. Physical QPU/channel integration is not selected. Original milestone acceptance, security review and live Devnet publication are not deferred or waived.
</deferred>
