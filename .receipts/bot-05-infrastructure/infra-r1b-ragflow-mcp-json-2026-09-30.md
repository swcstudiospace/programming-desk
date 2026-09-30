# INFRA — RAGflow MCP in .mcp.json (+ self-hosted gates)

2026-09-30 · bot-05-infrastructure

## Change
- Add `ragflow` HTTP MCP server to `.mcp.json` with `${RAGFLOW_MCP_API_KEY}`
- `runs-on: [self-hosted, Linux, X64]` on Quality Gates / sync (org hosted billing block)

## Rollback
Revert this PR.

No secrets committed.
