---
phase: 69-quantum-key-distribution-bb84-e91-entangled-state-ledger-sol
plan: 03
subsystem: quantum
tags: [drill, rest, auth, memo, devnet]
requires:
  - phase: 69-01
    provides: durable ledger and single-send Memo publisher
  - phase: 69-02
    provides: node-local BB84/E91 with public commitments
provides:
  - Shared-runtime drill whose all_passed flag requires a confirmed matching readback
  - Authenticated phase-69 REST families with seat checks before parse
affects: []
actuals:
  tokens: 22000
  tasks: 3
  commits: 1
tech-stack:
  added: []
  patterns:
    - Routes and the drill share one pool, engine, ledger, and publisher
    - A missing publisher prerequisite defeats all_passed and names the code
key-files:
  created: []
  modified:
    - services/desk-gateway/src/desk_gateway/quantum_qkd_mesh.py
    - services/desk-gateway/src/desk_gateway/config.py
    - services/desk-gateway/src/desk_gateway/server.py
    - services/desk-gateway/src/desk_gateway/quantum_anchor.py
    - services/desk-gateway/README.md
    - tests/test_quantum_teleportation_endpoints.py
key-decisions:
  - "Memo base58 readback cap scales with max_len; the 256-character default still bounds account keys"
  - "E91 stays outside the drill conjunction"
  - "Scripted Devnet confirmation is a fixture, not live acceptance"
patterns-established:
  - "Mutations are lead/systems; ledger reads are any authenticated seat"
requirements-completed: []
coverage:
  - id: D1
    description: "Unfunded shared drill keeps all_passed false and names rpc_url_not_configured"
    requirement: REQ-QTELEPORT-010
    verification:
      - kind: unit
        ref: "tests/test_quantum_teleportation_endpoints.py::test_unfunded_drill_keeps_all_passed_false"
        status: pass
    human_judgment: false
  - id: D2
    description: "Scripted publisher confirms one send and a matching readback"
    requirement: REQ-QTELEPORT-010
    verification:
      - kind: unit
        ref: "tests/test_quantum_teleportation_endpoints.py::test_scripted_devnet_drill_confirms"
        status: pass
    human_judgment: false
  - id: D3
    description: "Auth precedes parse; zero bit_length aborts with null QBER; proof tamper is valid false"
    requirement: REQ-QTELEPORT-011
    verification:
      - kind: unit
        ref: "tests/test_quantum_teleportation_endpoints.py"
        status: pass
    human_judgment: false
duration: 50min
completed: 2026-10-10
status: source-complete
---

# Plan 69-03: Shared drill and routes summary

The drill and the phase-69 routes now use one runtime. `all_passed` is true only after a confirmed Memo readback of an eligible summary. An unconfigured or unfunded publisher keeps it false.

## Evidence

- Parent command: `cd /tmp/desk-v51-implementation/services/desk-gateway && TMPDIR=/dev/shm .venv/bin/python -m pytest -q ../../tests/test_quantum_teleportation_endpoints.py ../../tests/test_quantum_qkd_mesh.py ../../tests/test_quantum_ledger_anchor.py --tb=line` → **87 passed in 61.81s**, exit 0.
- Unfunded drill: `all_passed` false, prerequisite `rpc_url_not_configured`, clean BB84 passed, Eve abort passed with `keys_agreed` false.
- Scripted fixture: `all_passed` true, one `sendTransaction`, confirmed anchor. This is not a live Devnet observation.
- Commit `5e22296` on draft PR #214.
- Follow-up `fa210d5`: zero-length E91, rejected counts, unknown lookups, unbound-worker 503, and a fresh balance read of 0 lamports at slot 509400169.

## Cutover

Gateway startup constructs the SQLite ledger and the Memo exporter. The old ledger, exporter, and drill classes are gone from `quantum_qkd_mesh.py`. Public session and drill JSON omit key bytes. The README tables name the route seats, the 1232-byte / 400000-CU / exact-readback limits, and the unobserved funding prerequisite.

## Not claimed

Live Devnet confirmation, requirement acceptance, independent approval, or a merge. The dedicated payer's last recorded balance is still 0.
