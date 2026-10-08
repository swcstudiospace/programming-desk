# Phase 3: Substrate Data Planes — Context

**Gathered:** 2026-10-08  
**Status:** Ready for research and planning  
**Mode:** Autonomous orchestration. Governed by `docs/upgrade-plan-desk-v2.md` §6, `ownership.yaml`, `docs/desk-operating-model.md`, and REQ-DATA-001 through REQ-DATA-038.

<domain>
## Phase Boundary

Phase 3 delivers Workstream B (Substrate data planes) and source step n3 (`docs/upgrade-plan-desk-v2.md` §6 and §12). It defines the five-store policy across GreptimeDB, TimescaleDB, DragonflyDB, Hindsight, and RAGFlow, establishes companion integration contracts and repository documentation, and coordinates memory, cache, relational coordination, and document search capabilities for Desk v2.

Explicitly out of scope for Phase 3:
- Tailscale network forwarder provisioning (governed under Phase 2).
- Desk Gateway FastAPI service implementation and per-seat OAuth routing (Phase 4 / n4).
- Grok Bot prompt assembly, marketplace packaging, and template creation (Phase 5 / n5).
- Cross-seat intake drills and acceptance testing (Phase 6 / n6).
- Final rollout synthesis and permanent retirement of `railway-app` (Phase 7 / n7).

</domain>

<decisions>
## Implementation Decisions

### Five-Store Architecture and Allocation Policy
- **D-01 (GreptimeDB Event Chain):** Append-only event store for tool calls, receipts, dispatches, intake, and seat heartbeats (`events_emit`). Enforces SHA-256 `hash`/`prev` chain, hourly devnet anchoring via `packages/ledger`, and 180-day hot retention before export. Strictly forbids unredacted payloads, secrets, or full transcripts.
- **D-02 (TimescaleDB Relational Coordination):** Transactional system of record for desk intake (`desk_intake` with `FOR UPDATE SKIP LOCKED`), Graph ID claims (`desk_claims`), 30-day idempotency set (`desk_idempotency`), verification receipts, seat rosters, and tool pack state. Retains hypertables `seat_heartbeat` and `tool_calls_1m` with continuous aggregates. Retains data while Graph ID is open + 90 days (aggregates 1 year).
- **D-03 (DragonflyDB Discardable Cache):** Redis-compatible discardable caching layer. 5-minute brief cache, 10-minute search/recall cache, 1-hour rate limit counters, and 24-hour mirror of idempotency keys. Discardable by design: outage or restart falls through to authoritative sources without data loss. Strictly forbidden as a durable queue, session store, or distributed lock.
- **D-04 (Hindsight Semantic Memory):** Hierarchical memory banks: `pd-desk` (shared; LEAD/QUALITY write, all read), `pd-<seat>` (seat-owned write), and `pd-lead-reports` (LEAD read). Replaces Agentmemory and local Claude Code stdio servers. Facts retained forever; weekly reflection prunes into mental models. Enforces prerequisite health/version check and TEI embedding dimension alignment. Retain calls without `receipt_path` or `source` URL are strictly refused.
- **D-05 (RAGFlow Document Retrievable Datasets):** Repository documentation and skill ingestion across `programming-desk`, `agent-substrate`, and product repos (`kanbanos`, `desklanes`, `clippyos`, `auctioning`). Chunked heading retrieval via TEI `bge-small` embedding on port 9380 without chat model dependency. Merges to `main` trigger re-ingest and retain the last 5 dataset versions. Receipts, secrets, and transcripts are strictly excluded from indexing.

### Companion Repository Integration Boundary
- **D-06 (Agent Substrate Boundary):** Substrate companion documents (`docs/data-planes.md`, `docs/railway-tailscale.md`, `.env.example`, `README.md`, `PROJECT.md`) define the external implementation contract. In this repository, integration is modeled, verified, and checked via contract schemas, mock/adapter interfaces, and gate validations.
</decisions>
