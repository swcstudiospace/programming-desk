---
phase: 69-quantum-key-distribution-bb84-e91-entangled-state-ledger-sol
plan: 01
subsystem: quantum
tags: [ledger, merkle, sqlite, solana-memo, devnet]
requires:
  - phase: 68-03
    provides: canonical teleport.completed event shape and injected append_event seam
provides:
  - Durable incremental-Merkle SQLite receipt ledger with metadata-bound binary leaves
  - Single-send SPL Memo Devnet exporter with exact readback admission
affects: [69-02, 69-03]
actuals:
  tokens: 42000
  tasks: 3
  commits: 1
tech-stack:
  added: []
  patterns:
    - Receipt returned only after the SQLite commit; historical prefixes immutable
    - Sign only after genesis, fee, and balance checks; prepared signature is never resent
key-files:
  created:
    - services/desk-gateway/src/desk_gateway/quantum_ledger.py
    - services/desk-gateway/src/desk_gateway/quantum_anchor.py
    - tests/test_quantum_ledger_anchor.py
  modified: []
key-decisions:
  - "Teleport leaves are 71 bytes and drill leaves 150 bytes, big-endian, full inclusion path, no padding or truncation"
  - "qkd.aborted is durable and never anchor-eligible"
  - "Wire caps (Memo 1021 bytes, packet 1232 bytes) fail with 413 before signing"
patterns-established:
  - Duck-typed append_event remains the only producer seam; the ledger does not import protocol modules
requirements-completed: []
coverage:
  - id: D1
    description: "Durable prefix, inclusion proof, and metadata binding"
    requirement: REQ-QTELEPORT-008
    verification:
      - kind: unit
        ref: "tests/test_quantum_ledger_anchor.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Memo message shape, signer hygiene, and single-send observation against a scripted RPC"
    requirement: REQ-QTELEPORT-009
    verification:
      - kind: unit
        ref: "tests/test_quantum_ledger_anchor.py"
        status: pass
    human_judgment: false
duration: 86min
completed: 2026-10-10
status: complete
---

# Plan 69-01: Durable ledger and Memo publisher summary

Receipt ledger and Devnet Memo exporter are implemented and parent-verified. Live funded publication is not claimed.

## Evidence

- Parent command: `cd /tmp/desk-v51-implementation/services/desk-gateway && TMPDIR=/dev/shm .venv/bin/python -m pytest -q ../../tests/test_quantum_ledger_anchor.py --tb=line` → **54 passed in 29.35s**, exit 0.
- Commit `7e3f2e6` on `bot-01-systems-backend/v5.1-faithful-simulator` (draft PR #214).
- Depth-16 proof runs on tmpfs scratch. The same code is fsync-bound on ext4 `/tmp` (about four minutes); durability settings are unchanged (`synchronous=EXTRA`, `journal_mode=DELETE`).

## Repairs inside the slice

Fee-envelope unwrapping, Merkle cascade termination, drill-leaf field coverage, attestation path encoding, and receipt-scoped single-send across later ledger growth. All are green in the final parent run.

## Not claimed

Live Devnet submit/readback (payer balance was 0; no fake slot). Native CLI decode. Full-repo gates, independent G-2, Greptile. 69-02/69-03 integration. A materialized depth-18 over-cap tree was not built; the 413 gate is the exact byte check, and the depth-16 memo is within cap.

Old in-module ledger/exporter classes inside `quantum_qkd_mesh.py` are still what `server.py` constructs. 69-03 owns that cutover. This plan does not re-export the new classes under the old module.
