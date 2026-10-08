# Phase 4: Desk Gateway and Contracts — Patterns & Invariants

## Invariant 1: Contract-First Primacy
Every tool served over an MCP endpoint must match its declared YAML contract in `contracts/tool-rosters/` or `contracts/tool-packs/`. Any tool schema change must follow Gate G-4 change documentation and consumer acknowledgements.

## Invariant 2: Perimeter Isolation & Auth Boundary
- No Grok Bot holds data plane credentials or joins the tailnet.
- Gateway listens on `127.0.0.1:8791` behind edge TLS.
- Tokens are seat-scoped; cross-seat access is forbidden with HTTP 403 `{"error": "wrong_seat"}`.
- External intake is isolated to `POST /v1/intake` using origin tokens; seat tokens are rejected with HTTP 403.

## Invariant 3: Failure Modes and Timeouts
- Strict 20-second deadline on all upstream calls.
- Read operations fail open (`not_configured` or structured empty result).
- Write and gated operations (`g5`, `g6`) fail closed.
- Stack traces from internal upstreams are completely stripped before returning error payloads.

## Invariant 4: Tool Count Caps
- Static seat tool rosters: 10–15 tools (LEAD 15, SYSTEMS 14, WEB 15, ANDROID 15, IOS 15, INFRA 15, QUALITY 15).
- Packs: Maximum 5 tools per pack.
- Total active live tools per seat capped at 20. Exceeding 20 live tools fails with `ceiling`.
