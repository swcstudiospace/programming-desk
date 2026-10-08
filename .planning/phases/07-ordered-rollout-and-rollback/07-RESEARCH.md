# Phase 7: Ordered Rollout and Rollback — Research & Findings

**Gathered:** 2026-10-08  
**Scope:** REQ-ROLLOUT-001 through REQ-ROLLOUT-013

## 1. Rollout Dependency Order & Lane Rules (n7.1)
- Progression:
  - Phase 2 (n2: Network Plane): Tailscale forwarders deployed in Ultrathink and Agent Substrate projects, ACL policy applied.
  - Phase 3 (n3: Substrate Data Planes): Data planes configured across Greptime, Timescale, Dragonfly, Hindsight, and RAGFlow.
  - Phase 4 (n4: Desk Gateway & Contracts): Desk Gateway skeleton, OAuth PKCE, MCP seat routing, intake endpoints.
  - Phase 5 (n5: Prompts, Skills, Templates, Plugin): Assembled prompts v1.1, 7 skills, marketplace plugin, 7 sanitized templates.
  - Phase 6 (n6: Fresh Acceptance & Intake): Fresh recipient bootstrap, double uplift, production loop invariants, failure drills.
  - Phase 7 (n7: Rollout & Rollback): Final cutover coordination, legacy retirement, PR sync, and merge clearance.
- Lane assignment:
  - n2 and n5: Lane C specialist tickets (INFRA, QUALITY, LEAD).
  - n3 and n4: Lane A Cursor Cloud Agents with second-uplift XML.
  - Lane B: Reserved exclusively for Ove requests.

## 2. Per-Node Rollback Procedures (n7.2)
- **Network Plane Rollback (REQ-ROLLOUT-002):**
  - Delete `tailscale-forwarder-ultrathink` and `tailscale-forwarder-substrate` services on Railway.
  - Re-enable TimescaleDB TCP Proxy (port `5432` mapped to public proxy) and public Greptime domain (`greptime.swcstudio.space`).
  - Underlying database volumes are completely preserved; zero data migration involved.
- **Substrate Plane Rollback (REQ-ROLLOUT-003):**
  - Restore prior environment file `substrate.env.bak` on Agent Substrate VPS.
  - Restart `substrate-mcp` service via systemd (`sudo systemctl restart substrate-mcp`).
- **Gateway Plane Rollback (REQ-ROLLOUT-004):**
  - Stop `desk-gateway` service (`sudo systemctl stop desk-gateway`).
  - Nginx configuration removes `/mcp/` and `/v1/` reverse proxy blocks.
  - Desk seats continue prior operation without gateway MCP tools.
- **Prompt Plane Rollback (REQ-ROLLOUT-005):**
  - Re-assemble v1.0 prompts using committed team roster (`grokbot/rosters/spectrumwebco.json`).
  - Pinned prompt hashes updated; recipient-breaking hardcoded IDs are avoided.
- **Template Plane Rollback (REQ-ROLLOUT-006):**
  - Re-publish previous template definitions in Grok Bot workspace.

## 3. Operational Discipline & Tracker Sync (n7.3, n7.4)
- Cutover windows announced in Desk channel before execution.
- LEAD emits dispatch notes as durable audit events.
- PR fields (Head SHA, review state, CI status) synced to Notion Agent Task Graph and Linear Spectrum Web Co project.
- Report to Ove in 1:1 enumerates every receipt path and documents honest `unverified` items.

## 4. Legacy `railway-app` Node Decommissioning (n7.5)
- Legacy subnet router node `railway-app` (`100.77.7.42`) is only decommissioned after Phase 6 acceptance is completely verified.
- Requires Gate G-6 destructive-operation approval with `blast_radius`, `operation`, `at`, and `approved_by`.
