# Phase 3: Substrate Data Planes — Patterns & Invariants

## Invariant 1: System of Record
GitHub is the immutable system of record for shipped code and repository state. Relational databases, memory banks, and caches are execution coordination tools. Shipped state claims without a corresponding Git commit and receipt are invalid.

## Invariant 2: Discardable Caching
Dragonfly must never hold the sole copy of any critical business data:
- Brief cache is an acceleration layer over Hindsight.
- Idempotency cache is a 24-hour fast reject filter over the 30-day Timescale table.
- Queue draining must never use Redis lists or Redis locks; Timescale `FOR UPDATE SKIP LOCKED` is required.

## Invariant 3: Memory Integrity & Attribution
- Memory writes require proof of provenance (`receipt_path` matching `^\.receipts/bot-0[0-6]-[a-z-]+/[A-Za-z0-9._-]+\.json$` or `source` URI).
- Memory reads return citations with bank attribution.
- Cross-bank mutation is prohibited (seats cannot write to other seats' banks).
