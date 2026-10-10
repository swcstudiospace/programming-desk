---
phase: 68-inter-cluster-quantum-teleportation-protocol-entanglement-sw
plan: 01
subsystem: quantum
tags: [quantum, density-matrix, born-sampling, numerical-kernel]
requires: []
provides:
  - Bounded synchronous 1-4 qubit state/density numerical kernel (quantum_state.py)
  - Gate-generated Bell frames, Born branch records, six-unitary explicit twirl
  - 30 deterministic mathematical regressions with parent-run evidence
affects: [68-02, 68-03, 69-02, 69-03]
actuals:
  tokens: 14909
  tasks: 1
  commits: 1
tech-stack:
  added: []
  patterns:
    - Immutable validated numerical objects with fail-closed near-limit composition
    - Squared-norm/trace/PSD 1e-9 single-window validation, no clamping or renormalization
key-files:
  created:
    - services/desk-gateway/src/desk_gateway/quantum_state.py
    - tests/test_quantum_state_kernel.py
  modified: []
key-decisions:
  - "Squared-norm acceptance window (not looser norm-only) so vector and density validation compose consistently"
  - "Every representable positive Born weight stays sampleable; only nonpositive weights are omitted"
  - "Strict integer correction bits; nonfinite/nonconverged eigensolver results fail closed"
  - "werner_twirl documented as six-unitary channel isotropizing Bell-diagonal inputs only, never implicit"
patterns-established:
  - "Kernel exceptions carry exact numeric windows; callers never see silently repaired data"
requirements-completed: []
coverage:
  - id: D1
    description: "Numerical kernel with immutable state/density objects, gates, branching, frames and oracles"
    requirement: REQ-QTELEPORT-001
    verification:
      - kind: unit
        ref: "tests/test_quantum_state_kernel.py (30 tests)"
        status: pass
    human_judgment: false
duration: 74min
completed: 2026-10-10
status: complete
---

# Plan 68-01: Numerical kernel summary

Bounded synchronous quantum-state kernel implemented, independently reviewed, repaired and parent-verified; distributed tier consumes it unchanged.

## Evidence

- `cd services/desk-gateway && uv run --no-sync python -m pytest -q ../../tests/test_quantum_state_kernel.py` → **30 passed** (exit 0).
- Boundary smokes (exit 0): rare ~1e-14 positive Born outcome sampled; accepted near-limit vector→density preserved without renormalization; noninteger correction bits, over-window squared norms and finite-extreme indefinite densities rejected.
- Mixed-state smoke (exit 0): 24 rank-two mixtures across 1–4 qubits match dense reference evolution to 1.2e-16; ±6e-10 trace tails sampleable; error-amplified tiny-branch conditioning rejected.
- Receipt `.receipts/bot-01-systems-backend/v5.1-kernel-postreview-verification.json`: G-1/G-3/G-4/G-5/G-6 pass; G-2 strict fails only on missing independent `approved_by` (expected, not self-stamped).
- Commit `c55f0ac` on `bot-01-systems-backend/v5.1-faithful-simulator` (draft PR #214).

## Review repairs (independent advisory + parent reproduction)

Rare-positive cutoff loss, inconsistent vector→density windows, noninteger measurement bits, missing eigensolver finiteness/convergence guards, wrong direct-Bell four-outcome expectations, inverted imaginary-coherence oracle, malformed invalid fixtures, exact-float pins, unseeded type-only tail, missing 0.99/0.25 teleport oracles — all reproduced before and repaired after; first corrected run was 5 failed/18 passed, final 30 passed.

## Boundaries

Numerical tier only. No worker/process/transport/resource/REST/QKD/ledger/chain claim. REQ-QTELEPORT-001–004 acceptance stays open pending phase-level distributed evidence. No physical/device-independent/production-secrecy claim.
