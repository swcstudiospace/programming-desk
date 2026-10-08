# Phase 4 Summary: External Intake Pipeline & Tool Packs (04-05)

## Executive Summary
Plan `04-05-PLAN.md` codifies the external intake ingestion pipeline, origin authentication, LEAD intake draining/acknowledgement, and dynamic tool pack lifecycle management.

## Key Deliverables & Verifications
1. **External Intake API (`POST /v1/intake`):**
   - Requires bearer token authentication against `INTAKE_TOKENS` (`origin:token` pairs).
   - Seat tokens attempting to call `/v1/intake` are rejected with HTTP 403.
   - Enqueues incoming requests (origin, title, ask, links, priority, requested_by, idempotency_key) into TimescaleDB `desk_intake` queue.
   - Emits intake event to GreptimeDB.
2. **LEAD-Exclusive Intake Tools:**
   - Non-LEAD endpoints attempting to call `desk_intake_next` or `desk_intake_ack` are refused.
   - `desk_intake_next`: Drains pending items using `FOR UPDATE SKIP LOCKED`.
   - `desk_intake_ack`: Records outcome (`accepted`, `rejected`, `in_progress`, `done`) and posts callback to origin (e.g., GitHub issue comment via `desk-intake.yml`).
3. **Dynamic Tool Pack Lifecycle & List Notifications:**
   - `desk_app_tools_load`: Loads application-specific tool packs for a specific ticket lifetime.
   - Pack tools are unloaded when the ticket completes.
   - Emits MCP `notifications/tools/list_changed` upon pack load/unload.
   - Fallback secondary connector path `/mcp/<seat>/packs/<app>` available when MCP client notification is unsupported.
