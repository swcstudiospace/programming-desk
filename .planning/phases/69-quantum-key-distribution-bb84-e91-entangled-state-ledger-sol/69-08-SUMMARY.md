---
phase: 69-quantum-key-distribution-bb84-e91-entangled-state-ledger-sol
plan: "08"
subsystem: quantum
status: source_complete
gap_closure: true
completed: "2026-10-10"
commits: [44fdc46, ede41cd]
key-files:
  modified:
    - services/desk-gateway/src/desk_gateway/quantum_qkd_mesh.py
    - services/desk-gateway/src/desk_gateway/quantum_node.py
    - services/desk-gateway/src/desk_gateway/server.py
    - tests/test_quantum_qkd_mesh.py
    - tests/test_quantum_node_transport.py
    - tests/test_quantum_teleportation_endpoints.py
    - services/desk-gateway/README.md
requirements-completed: []
---

# 69-08 — Repeater-fed E91, checked retirement and bounded ingress

## Change

E91 admits unchanged zero/short samples first, then resolves the supplied registered mesh's shortest route with lexical ties and the existing16-node bound before discovery, private binding or channel draws. No shadow graph or unregistered direct-pair fallback. Every disjoint private-key, public-witness and phase round requests its own real mesh entanglement with base_fidelity1 and purificationdisabled; actual returned density and known Pauli frame feed measurement.

Every round checks final-pair retirement before reconciliation or extraction. Unconfirmed cleanup failsresource_cleanup_unconfirmed, withholds commitments/keys and preserves resource quarantine. Both endpoints acknowledge private-key abort or the engine retains key-cleanup quarantine; no mutating retry. Original20000-round input and fixed worker history/cleanup headroom remain unchanged; long routes or warm histories may refuse admission and fail keylessly rather than shorten samples.

Activated QKDProtocolType in actual protocol/binding selection and QuantumBasis in actual rotation selection. Active types are QKDKeyExchangeSession and QuantumTeleportationDrillSimulator; removed obsolete names and migrated gateway/test consumers without aliases. JSON/REST shapes remain unchanged.

Parent serialized gateway/node ingress before the executors: supported decoderRecursionError becomes400invalid_json afterauth; finite-number validator remains iterative. Receipt limits are bounded to at most4ASCIIdecimal characters before one guarded int conversion, then1..1000; invalid limits become400invalid_limit.

## Parent-owned verification

- Complete root consumer suite: **667 passed in352.21s**, exit0,353.69s tool wall. Includes actual20,000-round four-node registered-repeater regression, no-route/no-effects, lexical-route tie, partialcapacity, actualreturnedstate/frame, failedreserve/consume/release and losttransfer quarantine boundaries. Command: `TMPDIR=/dev/shm uv run --project services/desk-gateway --no-sync python -m pytest -q --show-capture=no --junitxml=/tmp/desk-v51-gateway.xml tests`.
- Failing-before actual cleanup probe established256bits/usablekeys despite quarantinedpair andunreleasedleases. After repair: failedresource_cleanup_unconfirmed, extracted_bits0, both ownerskey_availablefalse, pairquarantined; unresolvedleases remain1/1 rather than falselyfreed. Public boundary smoke exit0in2.26s.
- Parent-only admission regressions3passed in1.91s; same authenticated gateway decoder seam returned400invalid_json, smokeexit0in2.06s. Not a fullPython3.12gateway run.
- Actual full20000repeater-only four-CLI-worker/gateway process proof completed. Historical earlier run exit0/tool1368.88s; subsequent actual run exit0/tool1125.58s established256bitendpointkeys,QBER0,CHSH2.828630008762767/lower2.3775443874507514,zeroactiveleasesallnodesandone-shotowneruse. Subsequentfive actualnumericaldrillstagespassedthenrealanchorinsufficient_balance/nullsignature-slot/all_passedfalse;usercapacity3/3/0/0preserved. DistinctmutationACKs86005/80993/100000/134967,peaks1/1/2/2. Processpredatesfinalerror-onlyguardrepairs;theirboundarieshaveactualseparateprobes/final752suite,notanunqualifiedfinalheadTCPclaim.
- Exact command history is retained in SYSTEMS receipt on draftPR214. Source executors ran no checks/commits; parent owned integration and commits.

## Review and acceptance boundary

CheckFinalE91Gap69 rechecked the clarified plan PASS before execution. LSP's external-root reference limitations did not authorize a cross-root rename; user checkout untouched. No new public route selector, history cap, shortening, retry, fake chain or requirement reduction. Original requirements-completed remains empty: signed Desk acceptance and final-head Greptile disposition are still required. GenuineMemo confirmation and positive liveall_passed remain blocked by funding; no hardware/DI/composable-secrecy, archive or merge claim.
