# Phase 4: Desk Gateway and Contracts — Context

**Gathered:** 2026-10-08  
**Status:** Ready for research and planning  
**Mode:** Autonomous orchestration. Governed by `docs/upgrade-plan-desk-v2.md` §7, `ownership.yaml`, `docs/desk-operating-model.md`, and REQ-GATEWAY-001 through REQ-GATEWAY-054.

<domain>
## Phase Boundary

Phase 4 delivers Workstream C (Desk Gateway and contracts) and source step n4 (`docs/upgrade-plan-desk-v2.md` §7, §10, §12). It establishes the contract-first per-seat gateway interfaces with authentic backend behavior, trusted authorization (OAuth PKCE with 24h access tokens and 30d refresh tokens), audit logging to GreptimeDB, intake routing (POST /v1/intake and LEAD intake tools), and public client reachability (`desk.swcstudio.space` over loopback 127.0.0.1:8791 behind nginx TLS).

Explicitly out of scope for Phase 4:
- Direct mutation of Grok Bot system prompts and assembly (Phase 5 / n5).
- Shared skill distribution and Team-only template publishing (Phase 5 / n5).
- End-to-end fresh-desk acceptance drills with human operator on iOS (Phase 6 / n6).
- Final cutover execution and railway-app retirement (Phase 7 / n7).

</domain>

<decisions>
## Implementation Decisions

### 1. Contract-First Governance and Rosters
- **D-01 (Contract-First Enforcement - G-4):** Tool rosters (`contracts/tool-rosters/*.yaml`) and tool packs (`contracts/tool-packs/*.yaml`) are owned by QUALITY (`bot-06-quality-security`). Any changes must satisfy Gate G-4 with consumer acknowledgements.
- **D-02 (Roster Ceilings and Seat Tools):** Each seat serves its core 8 tools plus seat-specific tools (LEAD 15, SYSTEMS 14, WEB 15, ANDROID 15, IOS 15, INFRA 15, QUALITY 15). Pack tools are dynamic (maximum 5 per pack, total live tools per seat capped at 20; 21st tool is rejected with `ceiling`).

### 2. Authorization and Security Boundaries
- **D-03 (OAuth PKCE & Scopes):** Gateway acts as an OAuth 2.0 AS with dynamic client registration and PKCE. Tokens grant strictly `seat:<seat>`. A token issued for seat A used against `/mcp/<seatB>` returns HTTP 403 `{"error": "wrong_seat"}`.
- **D-04 (Token Lifetimes):** Access tokens expire in 24 hours; refresh tokens expire in 30 days.
- **D-05 (Connector Key Testing):** `x-connector-key` header is restricted to local/smoke testing and cannot bypass production OAuth requirements.
- **D-06 (Network Isolation):** The gateway binds loopback `127.0.0.1:8791`. Nginx terminates public TLS for `desk.swcstudio.space`. Grok Bots communicate strictly over public HTTPS and never join the tailnet or access databases directly.

### 3. Execution, Audit, and Resilience
- **D-07 (Audit Trail):** Every tool invocation is audited to GreptimeDB (`agent_events`) and append-only local `audit.jsonl` with seat, tool, graph_id, task_id, duration_ms, status, and SHA-256 hash of redacted arguments.
- **D-08 (Failure Semantics):** Read operations fail open (empty result with structured reason). Write and gated (`g5`/`g6`) operations fail closed. Per-call upstream timeout is 20 seconds. Upstream stack traces are never leaked to clients.
- **D-09 (G-5 and G-6 Gate Tags):** `g5` tools require `rollback_plan` and `approval_id`; `g6` tools require `approval_id`. Calls missing required gate parameters are rejected before execution.

### 4. Intake Architecture
- **D-10 (Intake Routing):** `POST /v1/intake` requires an origin token (`INTAKE_TOKENS`). Seat tokens are rejected with HTTP 403. Work orders are enqueued in TimescaleDB `desk_intake`. Only LEAD's endpoint serves `desk_intake_next` and `desk_intake_ack`.
</decisions>
