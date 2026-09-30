# INFRA — RAGflow MCP in `.mcp.json` (MCP-only)

2026-09-30 · bot-05-infrastructure

## Change
- Add the `ragflow` HTTP MCP server to `.mcp.json`, authenticated with the
  `${RAGFLOW_MCP_API_KEY}` placeholder (resolved from the environment at runtime).

## Out of scope
- The self-hosted runner migration for Quality Gates has been reverted off this
  branch and lives on PR #32. This PR does not touch any workflow file.

## Verification
- `.mcp.json` ragflow entry is `type: http` with the `${RAGFLOW_MCP_API_KEY}` placeholder.
- `.github/workflows/gates.yml`, `.github/workflows/gates-template-sync.yml` and
  `ci/.github/workflows/gates.yml` are byte-identical to `main`.
- `pytest ci/tests/ -q` → 90 passed.

## Pending
- `approved_by` is intentionally absent; bot-06-quality-security stamps it.
  G-2 is expected to fail until then.
- The cloud session environment still needs `RAGFLOW_MCP_API_KEY` set.

## Rollback
Remove the `ragflow` block from `.mcp.json`. Takes effect on the next MCP client
start; no data or state involved.

No secrets committed.
