# Phase 4: Desk Gateway and Contracts — Research

**Date:** 2026-10-08  
**Scope:** Investigation of gateway architecture, endpoint schemas, authorization patterns, and upstream proxy requirements for Desk v2.

## 1. Roster and Contract Architecture
The contract layer defines exact interfaces for each seat:
- **Core 8 Tools:** `desk_brief`, `desk_docs_search`, `desk_memory_retain`, `desk_memory_recall`, `desk_ownership_resolve`, `desk_receipt_check`, `desk_event_emit`, `desk_doctor`.
- **Seat Tools:**
  - `LEAD`: intake_next, intake_ack, graph_register, graph_state, bus_start_job, bus_wait_job, roster_status (Total: 15).
  - `SYSTEMS`: index_query, events_query, cache, lsp_diagnostics, contract_propose, design_artifact_get (Total: 14).
  - `WEB`: lsp_diagnostics, vercel_deployments, vercel_promote, vercel_rollback, preview_check, bundle_secret_scan, contract_ack (Total: 15).
  - `ANDROID`: play_track_status, play_staged_rollout, play_halt_rollout, artifact_size_delta, lint_baseline_diff, contract_ack, app_tools_load (Total: 15).
  - `IOS`: testflight_status, appstore_phased_release, appstore_pause_release, entitlements_diff, review_risk_check, contract_ack, app_tools_load (Total: 15).
  - `INFRA`: railway_status, railway_logs, railway_variable_names, railway_redeploy, tailscale_status, vps_units, db_health (Total: 15).
  - `QUALITY`: gates_run, greptile_review, receipt_approve, waiver_record, contract_ack_status, supply_chain_check, secret_scan (Total: 15).
- **Tool Packs:**
  - `kanbanos`: api_smoke, supabase_query, push_test, feature_flags, crash_reports (Max 5).
  - `desklanes`: api_smoke, scoreboard_get, push_test, store_listing_get, crash_reports (Max 5).
  - `clippyos`: api_smoke, render_job_status, push_test, crash_reports (Max 4).

## 2. Authentication and Seat Scope Enforcement
- Endpoints:
  - `GET /.well-known/oauth-authorization-server`
  - `GET /.well-known/oauth-protected-resource/mcp/{seat}`
  - `POST /register`, `GET /authorize`, `POST /token`
- Token Structure:
  - Scoped to `seat:{seat}`.
  - Signed or mapped in memory/persistent store with 24-hour access token TTL and 30-day refresh token TTL.
  - Path-based enforcement: Accessing `/mcp/{seat}` with a token bearing `seat:{other}` returns HTTP 403 `{"error": "wrong_seat"}`.

## 3. Intake Plane Architecture
- `POST /v1/intake`:
  - Authorized exclusively with bearer token matched against `INTAKE_TOKENS` (`origin:token` pairs).
  - Rejects seat tokens with HTTP 403.
  - Persists request into `desk_intake` with idempotency key deduplication.
  - Emits intake event to GreptimeDB.
- LEAD Intake Tools:
  - `desk_intake_next`: Pulls next unclaimed item (`FOR UPDATE SKIP LOCKED`).
  - `desk_intake_ack`: Records status (`accepted`, `rejected`, `in_progress`, `done`) and posts callback/comment.

## 4. Operational Invariants and Resilience
- Loopback binding: `127.0.0.1:8791` (nginx handles TLS at edge).
- Upstream 20s timeout deadline per tool call.
- Secret redaction before Greptime audit.
- Read fail-open, write/gate fail-closed.
