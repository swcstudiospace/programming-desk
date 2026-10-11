---
phase: 68-inter-cluster-quantum-teleportation-protocol-entanglement-sw
plan: "04"
subsystem: quantum
status: source_complete
gap_closure: true
completed: "2026-10-10"
commits: [db1ac81]
tags: [density-matrix, numerical-oracles, psd]
key-files:
  modified:
    - services/desk-gateway/src/desk_gateway/quantum_state.py
    - tests/test_quantum_state_kernel.py
requirements-completed: []
---

# 68-04 — Basis-invariant numerical admission

Removed the duplicate incorrect `Gate2` definition. The positivity solver now uses the Hermitian average of conjugate entries without changing the stored density or tolerance policy. Added deterministic dense complex reference, trace, rare positive Born branch, conditioning and basis-permuted PSD counterexamples for the existing bounded 1–4-qubit kernel.

## Observed evidence

- Before-fix probe accepted an asymmetric density with minus fidelity `-1.1999999882661427e-09` and rejected its X-permuted equivalent.
- After-fix probe rejected that density in both basis orders; complex X correction retained unit fidelity within `1e-9` (exit 0, 0.21 s tool wall).
- Integrated six-file quantum suite: **265 passed in 62.21 s** (exit 0).
- Final broad consumer suite, repository-root invocation: **645 passed in 80.31 s** (exit 0, 81.61 s tool wall).
- Exact commands and unverified scope belong to `.receipts/bot-01-systems-backend/v5.1-faithful-simulator.json` on draft PR #214.

## Decisions and remaining gates

The synchronous exported API and strict raw `F >= 0.95` acceptance remain unchanged. No numerical result is a physical-device or cryptographic security assertion. Original REQ-QTELEPORT-001–004 remain linked to phase-wide distributed runtime evidence and independent approval; this source-plan summary does not self-approve them.
