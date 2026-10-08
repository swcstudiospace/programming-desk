# Phase 3: Substrate Data Planes — Research

**Date:** 2026-10-08  
**Scope:** Investigation of existing substrate coordination models, contracts, and data-plane requirements in `programming-desk`.

## 1. Five-Store Policy Architecture

### 1.1 GreptimeDB
- Target table: `agent_events`.
- Invariant: Append-only with cryptographic chaining (`hash`, `prev_hash`).
- Surface: HTTP SQL on port 4000.
- Purpose: Audit trail for all seat actions, tool invocations, receipts, and intake lifecycle events.

### 1.2 TimescaleDB
- Tables:
  - `desk_intake`: Transactional queue. Consumer concurrency handled via `FOR UPDATE SKIP LOCKED`.
  - `desk_claims`: Per-Graph-ID leases with expiration timestamps.
  - `desk_idempotency`: 30-day processed request keys.
  - `desk_receipts`: Staged and verified receipt records.
  - `seat_roster`: Registered seats and statuses.
  - `tool_pack_state`: Active/inactive tool pack states per seat and ticket.
- Hypertables:
  - `seat_heartbeat`: Time-series seat liveness telemetry.
  - `tool_calls_1m`: Continuous aggregate rollup of seat activity.

### 1.3 DragonflyDB
- Role: Ephemeral, discardable cache.
- TTL Matrix:
  - `desk_brief`: 300 seconds (5 minutes).
  - `docs_search` / `memory_recall`: 600 seconds (10 minutes).
  - Seat rate-limit counters: 3600 seconds (1 hour).
  - Idempotency key cache mirror: 86400 seconds (24 hours).
- Resilience Rule: Any Dragonfly failure/cache miss falls through to TimescaleDB or Hindsight transparently.

### 1.4 Hindsight
- Semantic memory engine with multi-bank isolation.
- Banks:
  - `pd-desk`: Global shared context. Writable only by LEAD (`bot-00`) and QUALITY (`bot-06`).
  - `pd-<seat>`: Seat-isolated working memory.
  - `pd-lead-reports`: Synthesis and executive summaries for LEAD.
- Constraints: Requires receipt path or external URI source; secrets and unverified claims rejected.

### 1.5 RAGFlow
- Document retrieval engine.
- Datasets: `programming-desk`, `agent-substrate`, `kanbanos`, `desklanes`, `clippyos`, `auctioning`.
- Embedding: TEI `bge-small`.
- Invariant: Ingestion triggered on merge to `main`; retains last 5 versions; excludes receipts, secrets, transcripts.
