---
phase: 69-quantum-key-distribution-bb84-e91-entangled-state-ledger-sol
plan: 02
subsystem: quantum
tags: [qkd, bb84, e91, toeplitz, chsh]
requires:
  - phase: 69-01
    provides: durable append_event sink that rejects key material
  - phase: 68-02
    provides: pool, kernel, and in-process workers
provides:
  - Node-local BB84/E91 measurement, reconciliation, and Toeplitz extraction
  - Public session projection with blinded commitments and no key bytes
affects: [69-03]
actuals:
  tokens: 28000
  tasks: 3
  commits: 1
tech-stack:
  added: []
  patterns:
    - Coordinator stores indices and public syndromes only; each worker holds its own bits
    - Locked epsilon set is fixed before the session and is not refit
key-files:
  created:
    - services/desk-gateway/src/desk_gateway/quantum_key.py
  modified:
    - services/desk-gateway/src/desk_gateway/quantum_qkd_mesh.py
    - services/desk-gateway/src/desk_gateway/quantum_node.py
    - tests/test_quantum_qkd_mesh.py
key-decisions:
  - "Relative intra-package imports so the helper resolves the sibling kernel module"
  - "Remote QKD transport is not in this slice; REST cutover is 69-03"
  - "The pre-69-03 ledger/exporter/drill classes remain at the bottom of quantum_qkd_mesh.py so current server imports still construct"
patterns-established:
  - "use_key is one-shot and returns an outcome, never key bytes"
requirements-completed: []
coverage:
  - id: D1
    description: "Clean BB84 establishment with equal node-local keys and a public sink event"
    requirement: REQ-QTELEPORT-006
    verification:
      - kind: unit
        ref: "tests/test_quantum_qkd_mesh.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "E91 witness on Phi+ versus product control, intercept-resend abort, 11/100 versus 12/100 gate"
    requirement: REQ-QTELEPORT-007
    verification:
      - kind: unit
        ref: "tests/test_quantum_qkd_mesh.py"
        status: pass
    human_judgment: false
duration: 40min
completed: 2026-10-10
status: complete
---

# Plan 69-02: QKD engine summary

BB84 and E91 now run as numerical sessions on the kernel and in-process workers. Key bytes stay on the node that measured them.

## Evidence

- Parent command: `cd /tmp/desk-v51-implementation/services/desk-gateway && TMPDIR=/dev/shm .venv/bin/python -m pytest -q ../../tests/test_quantum_qkd_mesh.py ../../tests/test_quantum_node_transport.py --tb=line` → **53 passed in 26.21s**, exit 0. Re-run after the sibling-module import change; same count.
- Runtime import check: `desk_gateway.quantum_key.bb84_state(0, "x")` returns a 1-qubit state.
- Commit `f786f35` on draft PR #214.

## Custody repair

The first executor draft computed both strings in the coordinator and installed them with `key_hex`. That path was removed before the commit. Alice prepares and announces syndromes; Bob measures, corrects, and tags his own string; both extract locally. The public session has commitments only. Tests compare the two private buffers and assert the engine has no `_private` store.

## Not claimed

Live Devnet, requirement acceptance, independent approval. Gateway QKD routes still call the old synchronous methods and fail closed until 69-03. The legacy ledger classes at the bottom of `quantum_qkd_mesh.py` are unchanged so process startup keeps working.
