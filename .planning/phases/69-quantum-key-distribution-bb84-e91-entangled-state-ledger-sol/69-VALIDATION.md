---
phase: "69"
slug: "quantum-key-distribution-bb84-e91-entangled-state-ledger-sol"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-09"
---

# Phase 69 — Validation Strategy

## Infrastructure and execution policy

Use the installed locked gateway pytest/httpx/cryptography/SQLite environment and native Solana CLI. No dependency upgrades, midpoint tests/build/lint, watch runs, source-text pins, public key material or mocked live acceptance. Parent verifies after integration. Runtime cwd: `/tmp/desk-v51-implementation/services/desk-gateway`; all GSD queries at `/tmp/desk-v51-audit`.

Quick command from runtime cwd: `uv run --no-sync python -m pytest ../../tests/test_quantum_qkd_mesh.py ../../tests/test_quantum_teleportation_endpoints.py -v`.

Failure direction: nonzero exit, collection error, zero tests collected, protocol/persistence/admission mismatch, missing real confirmation, or raw key leakage. Runtime and feedback latency are unmeasured.

## Per-task verification map

| Task | Plan | Requirement | Threat | Secure behavior | Evidence | Status |
|---|---|---|---|---|---|---|
| 69-01-01 | 01 | 008 | T-69-01 | Durable append-only canonical complete events; frozen historical prefix; aborted samples durability-only, eligible binary leaves only | Restart replay, exact inclusion proof, changed metadata/path/size rejection, corruption/truncation and concurrent writes; immutable snapshots; aborted sample never a publication preimage; replay recomputes metadata commitment plus exact binary bytes/hash/checkpoint | Pending |
| 69-01-02 | 01 | 009 | T-69-02 | Private external signer, fixed Devnet/Memo shape, bounded full proof, single send; all 8 INTEGRATE RPCs with fee/balance gates and expiry observation | Native decode/signature check on actual execution proof; wrong genesis/unsafe signer/packet/RPC error/readback mismatch and pending no-success tests; null-fee/insufficient-balance fail before sign/send; real depth-16 full-path byte measurement plus over-cap 413; no truncation/substitution/padding | Pending |
| 69-02-01 | 02 | 006,007 | T-69-03 | Independent private node candidates; sampled QBER, actual channel measurement; locked single epsilon/leakage policy | BB84 basis Born probabilities, real intercept/resend, strict 11% boundary, clean usable establishment, safe short/empty abort; ell_max=floor(H_after-2log2(1/EPS_PA)) with tag counted once, no combined log term, no second EPS_COR subtraction | Pending |
| 69-02-02 | 02 | 006,007 | T-69-04 | Bell-resource E91 witness; independent reconciliation and entropy-limited universal extraction; pool/inspect carry no QKD outcomes | Genuine Bell consumption/CHSH, disjoint phase estimation, recoverable and uncorrectable errors, counted leakage, private Alice/Bob final agreement without key serialization; bell receipts and inspect/snapshot DTOs hold allocation/lifecycle/frame/fidelity metadata only | Pending |
| 69-03-01 | 03 | 010,011 | T-69-05 | Same runtime REST/drill, explicit abort/withholding, no secret/URL control bypass; drill-summary eligible only after all physical stages; zero valid 200, negatives 400; cutover by behavior | Authenticated real gateway plus distinct node processes; every required numerical stage, shared durable receipts/proof and genuine Devnet submission/readback; zero bit_length/pair_count returns 200 aborted insufficient_sample with qber null; cutover proven by migrated behavior plus secret-exclusion, never absence pins | Pending |

Threat IDs are provisional; align with the planner's unique threat registers before final validation. All original requirement IDs must appear in final plan fronts; parser-null phase IDs do not waive manual coverage.

## Live acceptance and scope

A dedicated signer was created privately; the official airdrop failed and last observed balance was zero. The user selected external funding of its public Devnet address. Intent is not funding evidence. Exercise publisher code and all reachable numerical/runtime paths regardless. Live stage passes only with funded dedicated signer, fixed observed Devnet genesis, one actual signed transaction, non-null confirmed/finalized status, successful matching readback and observed execution slot/root/full proof. A local validator, mock RPC, local hash or CLI decode is insufficient.

Native CLI's previously decoded 871-byte dummy Memo proves wire shape only, not a numerical execution proof or chain compute/confirmation. Actual encoded packet must be <=1232 bytes, complete genuine path retained, no priority fee/transfer/program deployment. Confirmed append-only Memo cannot be erased; a correction needs a later authorized superseding record.

## Required security and persistence checks

- Raw/sifted/final keys, prefixes, capabilities, bearer credentials and signer bytes never enter public DTO, logs, ledger or chain.
- Minimum128 usable entropy/output bits; no digest-expansion fiction. Bob corrects/derives independently. Abort removes key availability at both nodes.
- Locked single finite-key policy: EPS_PE=1e-9, EPS_PA=1e-9, EPS_COR=2**-32 (32-bit tag counted ONCE), EPS_W=1e-6 fixed before sessions; ell_max=floor(H_after-2log2(1/EPS_PA)) with NO combined log term and NO second EPS_COR subtraction; trusted-device SIMULATOR numerical budget only; large clean sessions establish. Exact QBER gate 100*errors>11*count unchanged.
- Eligible leaves are versioned compact binary preimages (<=191B drill, ideally 150B) with the bound metadata commitment plus numeric counts; REST JSON is a projection only. Only teleport-success or all-stages-passed drill-summary leaves are anchor-eligible; aborted samples anchor nothing. Pool bell receipts and inspect/snapshot DTOs carry allocation/lifecycle/frame/fidelity metadata only, never QKD outcomes or candidates.
- E91 derives measured correlations from actual density; no copied classical bits or hidden Werner reconstruction.
- All Bell/session/abort events commit through the shared sink; current root may advance after publication while anchored prefix stays immutable.
- Corruption fails closed; no empty reset. Privileged whole-file rewrite is not defeated without external checkpoints; simulator claims are not physical/DI security.
- Missing credentials/config/resources, malformed input, unknown fields, packet overflow, null/pending/error confirmation and mismatched on-chain content cannot produce green results.

## Sign-off

Pending implementation, observed protocol/runtime/live-chain evidence, executed suite, independent security/review and honest receipt. No Nyquist compliance, all-passed drill, approval, milestone archive or merge-ready claim asserted.
