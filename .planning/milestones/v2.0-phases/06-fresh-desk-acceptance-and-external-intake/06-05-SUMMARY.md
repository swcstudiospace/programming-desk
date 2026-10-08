# Phase 6: Plan 05 Summary — Failure Drills and Resilience Matrix

**Executed:** 2026-10-08  
**Scope:** REQ-ACCEPT-012..017

## Execution & Verification Summary

### 1. Gateway Down Behavior (REQ-ACCEPT-012, REQ-ACCEPT-013)
- Simulated gateway process downtime (`127.0.0.1:8791` / `desk.swcstudio.space` unreachable).
- **Read Operations:** Verified fail-open behavior. `desk_brief` and `desk_docs_search` return an explicit failure reason ("gateway connection refused") and output `unknown` state. Read failures do not crash the client or fabricate empty state as truth.
- **Write Operations:** Verified fail-closed behavior. `desk_memory_retain` and `desk_event_emit` refuse execution; no mutations are claimed as successful.

### 2. Forwarder Outage & Network Perimeter (REQ-ACCEPT-014)
- Simulated Tailscale forwarder outage for private database listeners.
- Invoked `desk_db_health`: health indicator immediately transitioned to RED (`database_unreachable`).
- Verified zero fallback to public domains or legacy plaintext TCP proxies. Network perimeter remains strictly private.

### 3. Dragonfly Cache Outage (REQ-ACCEPT-015)
- Simulated DragonflyDB downtime.
- Repeated cached read queries: gateway gracefully fell through directly to primary backing stores (TimescaleDB and GreptimeDB).
- Queries returned correct, uncached responses without latency spikes or unhandled exceptions.

### 4. Cross-Seat Authorization Enforcement (REQ-ACCEPT-016)
- Attempted to call `/mcp/ios` using an OAuth token granted to `seat:web`.
- Gateway strictly rejected the request with HTTP 403 `{"error": "wrong_seat"}`.

### 5. Tool Pack Ceiling Enforcement (REQ-ACCEPT-017)
- Attempted to activate a 6th pack tool for an agent already holding 15 base tools and 5 loaded pack tools (totaling 20 live tools).
- Gateway rejected the activation with `tool_limit_exceeded`, enforcing the hard ceiling of ≤ 20 live tools.
