# Phase 4 Summary: Core Tools, Audit & Error Resilience (04-03)

## Executive Summary
Plan `04-03-PLAN.md` codifies the backend specifications for the core eight tools, GreptimeDB event auditing, Gate G-5/G-6 parameter enforcement, fail-open/fail-closed semantics, and 20-second execution deadlines.

## Key Deliverables & Verifications
1. **Core Eight Tool Semantics:**
   - `desk_brief`: Fetches Graph ID context, ticket state, and memory recall with 5-minute cache.
   - `desk_docs_search`: Queries RAGFlow/substrate document plane across repos with heading-aware chunk citations.
   - `desk_memory_retain`: Stores facts into `pd-<seat>` in Hindsight; requires valid `receipt_path` or `source` URL.
   - `desk_memory_recall`: Retrieves facts across `pd-<seat>` and `pd-desk` (plus `pd-lead-reports` for LEAD).
   - `desk_ownership_resolve`: Resolves `ownership.yaml` against `origin/main` according to Gate G-1 rules.
   - `desk_receipt_check`: Executes deterministic validation scripts (`check_receipt.py`, `check_secrets.py`, `check_rollback.py`) without modifying git state.
   - `desk_event_emit`: Appends structured seat events to GreptimeDB via substrate `events_emit`.
   - `desk_doctor`: Exposes `check`, `register`, `install_prompt`, and `repair` operations with bounded repair authority.
2. **GreptimeDB Audit Logging:**
   - Every tool call emits an audit record to `agent_events` and append-only local `audit.jsonl`.
   - Audit payload includes `surface="grok-bot"`, `seat`, `tool`, `graph_id`, `task_id`, `ok`, `ms`, and SHA-256 hash of redacted arguments.
3. **Gate Parameter Enforcement:**
   - `g5` tagged tools require both `rollback_plan` and `approval_id`.
   - `g6` tagged tools require `approval_id`.
   - Missing gate arguments trigger immediate call refusal before execution.
4. **Resilience & Failure Modes:**
   - Upstream execution deadline enforced at 20 seconds per call.
   - Read operations fail open (empty result with structured failure reason).
   - Write and gated operations fail closed.
   - Upstream stack traces are stripped before client response delivery.
