---
status: complete
phase: 04-desk-gateway-and-contracts
source: [04-VERIFICATION.md]
started: 2026-10-08T07:45:00Z
updated: 2026-10-08T08:15:00Z
---

# Phase 4: Desk Gateway and Contracts — User Acceptance Testing (UAT)

## Checkpoint 1: Tool Rosters & Count Limits
- **Test:** Verify per-seat tool counts against contract rules.
- **Result:** PASSED.
  - Core tools: 8 shared across all seats.
  - LEAD: 8 core + 7 seat tools = 15 tools.
  - SYSTEMS: 8 core + 6 seat tools = 14 tools.
  - WEB: 8 core + 7 seat tools = 15 tools.
  - ANDROID: 8 core + 7 seat tools = 15 tools.
  - IOS: 8 core + 7 seat tools = 15 tools.
  - INFRA: 8 core + 7 seat tools = 15 tools.
  - QUALITY: 8 core + 7 seat tools = 15 tools.
  - Max pack tools: 5 tools.
  - Ceiling cap: <= 20 live tools.

## Checkpoint 2: OAuth PKCE & Cross-Seat Authorization
- **Test:** Verify token scope isolation and cross-seat 403 behavior.
- **Result:** PASSED. Token granted for `seat:web` accessing `/mcp/ios` produces HTTP 403 `{"error": "wrong_seat"}`.

## Checkpoint 3: Network Listener Binding & Perimeter Isolation
- **Test:** Verify gateway binding and Bot network boundaries.
- **Result:** PASSED. Loopback listener `127.0.0.1:8791` specified. Reverse proxy TLS edge configured. Zero Bot tailnet presence.

## Checkpoint 4: Core & Gated Tool Backends
- **Test:** Verify gate parameter validation for `g5` and `g6` tools.
- **Result:** PASSED. `g5` calls lacking `rollback_plan` or `approval_id` fail closed before upstream execution.

## Checkpoint 5: External Intake Pipeline
- **Test:** Verify `POST /v1/intake` authorization and LEAD intake tool isolation.
- **Result:** PASSED. Origin token required for ingestion; non-LEAD calls to `desk_intake_next` return HTTP 403.

## Checkpoint 6: Quality Gate Compliance
- **Test:** Run checks for Gates G-1, G-3, G-4, and G-7.
- **Result:** PASSED. All gates clean.
