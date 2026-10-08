# Phase 4 Summary: OAuth PKCE Authorization & Network Isolation (04-02)

## Executive Summary
Plan `04-02-PLAN.md` codifies the authorization architecture, seat scope isolation, loopback listener binding, and perimeter network isolation for Desk Gateway.

## Key Deliverables & Verifications
1. **OAuth 2.0 PKCE & Seat Scopes:**
   - Per-seat client identification with PKCE code challenge.
   - Issued tokens are scoped strictly to `seat:<seat>`.
   - Access token lifetime: 24 hours. Refresh token lifetime: 30 days.
2. **Access Isolation & Cross-Seat Protection:**
   - Requests to `/mcp/<seat>` require an authenticated token possessing `seat:<seat>`.
   - Cross-seat token usage returns HTTP 403 `{"error": "wrong_seat"}`.
   - Connector key header (`x-connector-key`) is restricted strictly to local smoke testing and cannot bypass OAuth in production.
3. **Network Perimeter & Listener Binding:**
   - Gateway binds strictly to loopback `127.0.0.1:8791`.
   - Nginx handles TLS termination on the VPS edge (`desk.swcstudio.space`).
   - Grok Bots communicate over public HTTPS; they never join the tailnet and hold zero database credentials.
   - Environment variables isolate data plane access tokens (`substrate.env`) from gateway tokens (`gateway.env`).
