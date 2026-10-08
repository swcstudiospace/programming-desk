# Phase 5: Prompts, Skills, Templates, Plugin — Patterns

## Pattern 1: Deterministic Prompt Rendering
Prompt sources (`prompts/bot-0*.xml`) and shared directives (`prompts/_shared/core-directives.xml`) are templates containing uppercase placeholders. Assembly consumes an explicit roster file (`grokbot/rosters/<team>.json`) and outputs fully rendered XML where every placeholder has been resolved. Any remaining placeholder results in non-zero exit code.

```bash
bash scripts/assemble-prompts.sh --roster grokbot/rosters/spectrumwebco.json --check
```

## Pattern 2: Template Sanitization and Isolation
Grok Bot Team-only templates contain only high-level rules, role charters, public gateway links, and skill bindings. All credentials, tokens, private network identities (Tailscale MagicDNS, 100.x/10 IPs), internal domains (`railway.internal`), and literal UUIDs are strictly excluded.

```
Template File Structure:
- # <Role Name> (<SEAT>)
- ## Description (Charter, First Run command, Public Gateway MCP URL)
- ## Enabled skills (desk-bootstrap, desk-production-loop, desk-doctor, verification-receipts, seat skills)
- ## Routines (Paused until desk_doctor check is green)
- ## Avatar (Relative asset path)
```

## Pattern 3: Doctor Verification Report Matrix
`desk_doctor check` validates 7 core subsystems:
1. **Prompt:** SHA-256 matches gateway render at `{{DESK_ROSTER_VERSION}}`.
2. **Skills:** All declared `<skill>` entries exist in private library.
3. **Memory:** Hindsight `/health` reachable; `pd-<seat>` exists; redacted probe roundtrips.
4. **Tools:** Contract match (10–15 tools base; <= 20 live tools with pack); `g5`/`g6` marked.
5. **Connector:** OAuth token valid for seat; cross-seat call returns HTTP 403.
6. **Roster:** 7 UUIDs registered; channel ID registered; LEAD in group, QUALITY out; heartbeat fresh.
7. **Substrate:** `desk_event_emit` lands in GreptimeDB; `desk_docs_search` returns hits.

## Pattern 4: Marketplace Plugin Manifest
The Cursor Team Marketplace plugin specifies the 7 MCP servers and bundles skills into a single installable package.
```json
{
  "name": "swc-programming-desk",
  "version": "1.0.0",
  "publisher": "swcstudiospace",
  "description": "Grok Bot and Cursor integration for Programming Desk v2",
  "connectors": {
    "desk-lead": { "url": "https://desk.swcstudio.space/mcp/lead" },
    "desk-systems": { "url": "https://desk.swcstudio.space/mcp/systems" },
    "desk-web": { "url": "https://desk.swcstudio.space/mcp/web" },
    "desk-android": { "url": "https://desk.swcstudio.space/mcp/android" },
    "desk-ios": { "url": "https://desk.swcstudio.space/mcp/ios" },
    "desk-infra": { "url": "https://desk.swcstudio.space/mcp/infra" },
    "desk-quality": { "url": "https://desk.swcstudio.space/mcp/quality" }
  }
}
```
