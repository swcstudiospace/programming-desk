# Phase 68 Gap Closure — Shared Worker/Client Contract Addendum

**Status:** Planning detail for gap plans 68-04 through 68-07. Not a completion, verification, or merge-readiness claim. No commits made.
**Parent contract:** /tmp/desk-v51-gap-contract.json (phase68_slices). Old phase artifacts (68-01..03 PLANs/SUMMARYs, INTERFACES, VERIFICATION) are read-only and unchanged.

## 1. Error taxonomy (frozen by 68-05, consumed by 68-06)

- `NodeTransportUnavailable`: definitive proof nothing was sent (connect-time/DNS failures only). Callers may treat the operation as not applied.
- `NodeTransportAmbiguous`: post-send uncertainty (timeouts, ReadError, WriteError, HTTP 5xx, invalid JSON on mutating calls). Callers MUST quarantine, never report `worker_refused`, never retry the mutation.
- `NodeCommandFailed`: explicit worker refusal with status and code. Callers release untouched reservations.
- Read-only calls (`inspect` probe) use deadline semantics, never ambiguity.

## 2. Instance binding (frozen by 68-05, consumed by 68-06)

- Mutating commands pin the instance captured at reservation time (original-instance binding) for the life of the operation.
- Default `inspect` is an unscoped read-only probe carrying no cached instance; on reply it refreshes the cached instance for future reservations only.

## 3. At-most-once (frozen by 68-05)

- Replay digests cover the full validated payload including `rho_matrix` for `stage_conditional_state`. Any changed field under a reused operation ID returns `operation_conflict`.
- Keep2048 full acknowledgements plus exact operation-ID digest tombstones up to262144 per instance, never evicting tombstones. Reserve1088 slots for terminal cleanup (max1024 leases+64 QKD records): new non-cleanup effects refuse at261056 before effects/draws; scoped terminal release/abort/key-use uses reserved slots and retains tombstones. Readonly/cached replay remains available; evicted replies return409 operation_expired.20000 E91 pairs at<=10 effects/endpoint/pair fit with headroom; test saturation including cleanup.
- Lease IDs are independently bounded (pass the same 128-character check `release` enforces); every issued lease is releasable.

## 4. Pool lifecycle (frozen by 68-06, exposed by 68-07)

- Batch operations (`consume_pairs`, `discard_pairs`, `release_reservation`) prevalidate the whole batch before mutating any record.
- `register_output` removes transferred survivor leases from retired inputs at registration; each lease has exactly one owning live record.
- New outputs stay unavailable until their completion event commits; failed receipts quarantine the output.
- `QuantumTeleportationProtocol.release_teleport_output(session_id, receiver, operation_id)` owns release: success persists until explicit owner release; unknown404, receiver mismatch403, new-operation re-release409, same-operation replay returns acknowledgement. Result `output` contains session_id, receiver, resource_id, lease_id, instance_id, and available/released status only. HTTP: `POST /v1/quantum/teleportation/outputs/release` (68-07).
- Uncertain reserves are tracked by (operation ID, resource ID) and reclaimed through worker inspection; mutations are never retried.

## 5. Numerical predicate (frozen by 68-04)

- PSD validation runs over the Hermitian part; stored rows are never rewritten; tolerances unchanged.
- Reported `p_accept` derives from actual joint-state equal-bit branches; retained purification density stays exact untwirled.

## 6. Explicit non-scope (owned elsewhere)

- QKD session stores, key capabilities, `use_key` digest, QKD/anchor/drill routes, and drill-worker cleanup: phase 69 (69-05/69-06/69-07). Phase 68 provides the lease/correction-reclaim and release primitives only.
- Parent-owned: final six-file suite, real worker-process/HTTP smoke, 69 truth-YAML correction, 69 verification rescoring, commits, and approvals.
- Before-fix baselines in force: parent before-smoke (exit 0) observed the asymmetric-counterexample acceptance, minus fidelity -1.1999999882661427e-09 with X-permutation rejection, and shared-ledger second-writer IntegrityError; long-Memo base58 decode already passes (296342361 already repaired, no action).
