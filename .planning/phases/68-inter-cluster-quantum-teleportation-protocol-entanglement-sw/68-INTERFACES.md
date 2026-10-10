# Phase 68 — Finalized Interfaces, Dependencies, and Source Coverage Audit

**Status:** Planning detail; not a completion, verification, or merge-readiness claim. No commits made.
**Parent DAG:** 68-01 → 68-02 → 68-03 (waves 1/2/3, phase-local). Cross-phase: 68-02 outputs consumed by 69-02/69-03; 69-01 durable sink lands parallel against the fixed `append_event` contract below.

## 1. Finalized cross-phase method/DTO fields (converged with PlanQkd)

- `BellStateType` remains in `quantum_teleportation.py` with unchanged wire values (`PHI_PLUS/PHI_MINUS/PSI_PLUS/PSI_MINUS`). `quantum_state.BellState` accepts the validated kind **string**; it never imports `BellStateType` (cycle avoidance). No re-export shims, no deprecated aliases; every affected caller is cut over.
- Kernel (`quantum_state.py`, sync, no I/O): `QuantumStateVector.from_qubit/tensor/apply_single/apply_cnot/density`, `QuantumDensityMatrix.from_statevector/bell_mixture/tensor/apply_single/apply_cnot/branches_z/measure_z/partial_trace/permute/fidelity_pure/to_public_matrix`, 1–4 qubits, big-endian, RNG protocol `random()->float` (default `secrets.SystemRandom`).
- Resource tier (uniformly async): `BellPairPool` sole lifecycle authority (`create_pair/consume_pair/reserve`, sync snapshots, injected RNG/transport/`append_event` sink); `EntanglementPurifier` returns BBPSSW branch records; `QuantumRepeaterMesh` (`register_node/register_link`, ≤16-node routes) + `EntanglementSwapper`; `QuantumTeleportationProtocol` with `TeleportationSession/ClassicalCorrection` DTOs; success = F>=.95 + applied correction + acks + committed receipt.
- Worker/transport fixed surface: `reserve/apply_circuit/measure/stage_conditional_state/correct/transfer/release/inspect`; receiver computes `x=m_x^frame_x`, `z=m_z^frame_z` and applies real X/Z to the **staged conditional rho** (never original amplitudes). `LocalNodeTransport` (unit semantics) vs `RemoteNodeTransport` (operator URLs, `trust_env=False`, no redirects, scoped tokens, overall deadline).
- Shared sink (converged): sole append path `append_event(event: Mapping) -> FrozenReceipt` (`receipt_id/seq/leaf_digest_hex/tree_size/prefix_root_hex`); 68 emits `bell.*/teleport.*/swap.*/purify.*` only and treats the sink duck-typed (no ledger import); 69 owns snapshot/proof/codec/attestation detail and `qkd.*/drill.*/anchor.*` types; every lifecycle/abort emits once; payloads are public allowlisted mappings, never key material. Per-node separately-blinded commitments; no exchanged private blinding.
- Config: `QUANTUM_NODE_ENDPOINTS/TOKENS/LINKS` (+69 adds `QUANTUM_SOLANA_RPC_URL/SIGNER_PATH`); worker reads own `QUANTUM_NODE_TOKEN`; CLI carries node/capacity/port only. Gateway mutations lead/systems; reads any authenticated seat; 401 vs 403 distinguished; auth precedes parse/side effects.

## 2. Parent-frozen notes recorded (not planned scope)

- `specless_probe_fallback` key absent → default ON applies; config untouched by these plans.
- Assumption-delta scan: both phases false (no assumption drift).
- Phase-69 QKD zero-count compat (fixture-facing): `200` public `aborted/insufficient_sample` with `qber:null`, no keys; negative/bool/string/excess inputs `400`. Recorded for 69-02/69-03 fixtures; no 68 behavior depends on it.
- Product symbol changes must query references first (including new interface fields) across the full pool/mesh surface; per parent LSP scoping the only consumers are qt/qkd/server/root quantum tests. Decorated symbols: LSP symbol lines may start at `@dataclass`; use class line+1 for references (`TeleportationResult` actual 258). Bounded Pyright-stdio is the allowed fallback; partial/null references are never exhaustiveness proof.
- Edge probes ran with scoped original requirement descriptions plus explicit shapes (Bell-physics terms, otherwise heuristic miss): phase-68 31 applicable edges, all unresolved — hence the per-category must_haves below. No new scope values invented; user values preserved; descriptor-less items stay flagged unverified as workflow.
- Verify-command paths and failure directions are probed by the parent before checker review; verify blocks below pin absolute runtime cwd with immediate `fails_when`.

## 3. Source coverage audit (REQ × edge-category → plan)

Categories: boundary / adjacency / empty / ordering / precision / idempotency / concurrency (+ encoding for IO text).

| Req | Required categories | Covered in | How |
|---|---|---|---|
| REQ-001 | boundary, adjacency, empty, ordering, precision, idempotency, concurrency | 68-01 (math) + 68-02 (allocation) | Kernel truths + pool truths; artifacts `quantum_state.py`, `quantum_teleportation.py`, `quantum_node.py` |
| REQ-002 | boundary, adjacency, empty, ordering, precision, idempotency, concurrency | 68-01 (swap identities) + 68-02 (BSM/routing) | 64-branch oracle + mesh truths |
| REQ-003 | boundary, empty, encoding, precision, idempotency, concurrency | 68-01 (kind validation, boundary) + 68-02 (teleport protocol) | 16-branch oracle + receiver-gate truths |
| REQ-004 | boundary, adjacency, empty, ordering, precision, idempotency, concurrency | 68-01 (BBPSSW oracles) + 68-02 (pool-mediated purify) | Accept/reject + untwirled-retention truths |
| REQ-005 | empty, encoding, idempotency, concurrency | 68-03 | REST validation/auth/outcome truths |

No deferred ideas exist in 68-CONTEXT; no research out-of-scope items are taken; nothing is silently dropped. Every row above resolves to explicit `must_haves.truths` in the cited plan — there are zero unplanned items, so no phase split is recommended. Threat IDs T-68-01…T-68-07 are unique across the three plans (ASVS 5.0, L1, high-severity blocking). Decision D-01 is cited in every plan objective, task action, and threat model.
