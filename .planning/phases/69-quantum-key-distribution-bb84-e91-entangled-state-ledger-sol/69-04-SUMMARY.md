---
phase: 69-quantum-key-distribution-bb84-e91-entangled-state-ledger-sol
plan: "04"
subsystem: quantum
status: source_complete
gap_closure: true
completed: "2026-10-10"
commits: [833cff8]
tags: [sqlite, merkle, solana-devnet, single-send]
key-files:
  modified:
    - services/desk-gateway/src/desk_gateway/quantum_ledger.py
    - services/desk-gateway/src/desk_gateway/quantum_anchor.py
    - tests/test_quantum_ledger_anchor.py
requirements-completed: []
---

# 69-04 — Durable prefixes and strict single-send publication

Same-file appenders refresh committed history under `BEGIN IMMEDIATE` before deriving sequence, predecessor and root. Replay binds searchable columns and typed execution bytes to canonical metadata and frozen checkpoints. Receipt lookup is indexed and complete; list cost is proportional to the requested bound; returned proofs cannot mutate cached metadata.

Per-receipt SQLite publication claims have one winner regardless of later prefix choices. Ordinary aborted leaves remain durable but publisher-ineligible. A prepared signature is immutable; an interrupted or ambiguous send is observed, never re-signed or resent. Historical status/readback can recover an aged signature.

## Post-review corrections

RPC replies are streamed under 64 KiB wire and decompressed budgets and an overall deadline. JSON-RPC envelopes, required explicit error fields, nonnegative u64 chain numbers, exact legacy message/header/keys/instructions and prepared signature are checked before confirmation. Program-name fallbacks cannot bypass instruction admission. Complete Memo/proof byte caps remain unchanged.

The original base58 long-Memo decoder already worked and was not rewritten. A fresh-path indentation defect and missing eligibility admission were repaired during parent integration. Three checkpoint-corruption fixtures now guarantee changed bytes instead of sometimes replacing an already-equal hex prefix.

## Observed evidence

- Before/after same-receipt, different-prefix claim probe: `true/true` became `true/false` across two same-file ledger objects (after exit 0, 0.29 s).
- Fresh unconfigured publisher now returns typed `503 rpc_url_not_configured`, not `None` (exit 0, 0.50 s; no chain RPC).
- Corrupted eligible-payload startup probe returned `LedgerCorruptError`; the allegation that startup leaks raw `ValueError` is refuted by the constructor's existing exception normalization.
- Integrated six-file quantum suite: **265 passed**. Final broad suite: **645 passed in 80.31 s**, exit 0.

## External acceptance blocker

No live Memo signature, confirmed slot or matching Devnet readback was observed. Public payer `52WUE6dEz5VsaeV328qTTfWHm3Swbx4BXHFRqKvVGShv` last observed at **0 lamports**, confirmed slot **509446760**. Official `requestAirdrop` returned HTTP 429 with `Retry-After: 86400`; no rate-limit evasion or human-only faucet automation. REQ-QTELEPORT-009 and live REQ-QTELEPORT-010 acceptance remain blocked. Scripted RPC success is regression evidence only. Independent approval and Greptile dispositions remain required.
