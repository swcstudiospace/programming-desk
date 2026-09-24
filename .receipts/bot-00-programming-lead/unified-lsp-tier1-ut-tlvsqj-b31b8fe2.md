# Unified LSP Tier-1 spike — design notes

graph_id: `ut-tlvsqj-b31b8fe2`  
runtime: cursor-cloud  
owner of this note: bot-00-programming-lead  
paths chosen this run (they were ASSUMPTIONS in the uplift; they were not already in the repo):

- INFRA broker: `infra/unified-lsp-broker/` (bot-05, via `infra/**`)
- WEB MCP adapter: `web/mcp-unified-lsp/` (bot-02, via `web/**` and `**/*.ts`)
- Fixture workspace ASSUMPTION: `infra/unified-lsp-broker/fixtures/`

`docs/**` is QUALITY-owned except a few LEAD files. This note stays under `.receipts/bot-00-programming-lead/` so it does not edit a QUALITY doc. `docs/gotxcot-cloud-pipeline.md` was not changed.

## n2 — Broker vs MCP vs optional WebSocket

| Piece | Seat | Process | Transport |
|---|---|---|---|
| Broker lifecycle, registry, language-server children | INFRA `bot-05-infrastructure` | `infra/unified-lsp-broker/broker.py` | Unix-socket newline JSON, box-local |
| Agent surface | WEB `bot-02-web-edge` | `web/mcp-unified-lsp/server.ts` | MCP stdio (newline JSON-RPC). No listen socket |
| Share plane | INFRA, off unless `--ws` | same broker | WebSocket, loopback only (`127.0.0.1`, `localhost`, `::1`) |

MCP stdio is the primary agent surface. The adapter shells out to `broker.py rpc`. It does not open WebSocket or TCP.

WebSocket is optional and refuses non-loopback hosts (`ws_host_forbidden` for `0.0.0.0`). If it is absent, stdio MCP still works. The MCP proof starts the broker without `--ws`.

Lifecycle states implemented: `cold`, `ready`, `serving`, `degraded`, `stopped`. Clean stop kills language-server process groups and leaves `state.json` at `stopped`.

Structured errors (broker code, passed through MCP `isError` tool results): `workspace_unbound`, `broker_not_running`, `broker_not_configured`, `language_not_tier1`, `language_server_missing`, `language_server_failed`, `install_not_executed`, `diagnostics_timeout`, `workspace_escape`, `file_not_found`, `ws_host_forbidden`, `invalid_arguments`.

Broker ↔ MCP method list lives in `infra/unified-lsp-broker/broker_mcp_boundary.yaml`. That file is **not** `contracts/**`. QUALITY owns the contract surface. Promoting the boundary into `contracts/` with consumer acks is a follow-up and blocks calling the cross-seat interface merged. This spike implements both sides against that local description in one branch because Lane A was dispatched as a single draft PR.

## n3 — Tier-1 registry

Strategy: registry + install-on-demand. The registry is `infra/unified-lsp-broker/registry/tier1.json`. Tier-1 ids are only `tsjs` (TypeScript and JavaScript), `python`, and `go`. `rust` returns `language_not_tier1` and is not installed.

Default install writes a state-dir wrapper that execs the in-repo fixture language server (`fixture_ls.py`). That is the demonstrable on-demand install in this environment. The fixture publishes a diagnostic for each line containing `ulsp-diag:`.

Production plans are recorded and **not executed**:

| Id | Command | Install runner |
|---|---|---|
| tsjs | `typescript-language-server --stdio` | npm packages `typescript-language-server`, `typescript` (unpinned) |
| python | `pyright-langserver --stdio` | npm package `pyright` (unpinned) |
| go | `gopls serve` | `golang.org/x/tools/gopls@latest` (unpinned) |

Pins are an ASSUMPTION. Unit D / n6 owns supply-chain review. `ULSP_SERVER_MODE=production` returns `install_not_executed` instead of hitting the network.

Per-language isolation: a crash of the Python session (spike hook `arm_crash`) marks that session failed, moves the broker to `degraded`, and leaves TS/JS and Go diagnostics working. One restart is attempted, then the language stays failed.

Fixture paths (ASSUMPTION):

- `infra/unified-lsp-broker/fixtures/tsjs/sample.ts`
- `infra/unified-lsp-broker/fixtures/tsjs/sample.js`
- `infra/unified-lsp-broker/fixtures/python/sample.py`
- `infra/unified-lsp-broker/fixtures/go/sample.go`

The `.go` fixture is covered by `infra/**` → bot-05. There is no `**/*.go` rule. A Go file outside `infra/**` would be UNOWNED, not SYSTEMS. Proposed QUALITY edit, **not applied** (ownership.yaml is bot-06):

```yaml
- pattern: "**/*.go"
  owner: bot-05-infrastructure
```

Place it with the other language rules only after QUALITY decides the seat. Do not assign Go to SYSTEMS by silence. This spike does not add a Go module.

Python under `infra/**` resolves to bot-05 because `infra/**` is later than `**/*.py`. That was checked with `check_ownership.py`. INFRA's declared languages are HCL, YAML, and Bash; Python is a seat-language stretch chosen so LSP framing is testable, and it is recorded here rather than treated as a SYSTEMS claim.

## n4 / Unit E — Fork baseline

Decision: **greenfield spike that adapts patterns**. No candidate was forked or vendored.

Sources read for the comparison (public READMEs, 2026-09-24):

- https://github.com/isaacphi/mcp-language-server
- https://github.com/t3ta/mcp-language-server
- https://github.com/beruang/lsp-mcp
- https://github.com/code-yeongyu/lsp-tools-mcp

| Candidate | Agent transport | Multi language server | Install on demand | Why it is not the baseline |
|---|---|---|---|---|
| isaacphi/mcp-language-server | MCP stdio; child LSP stdio. One `--lsp` process | No | No (operator preinstalls) | Best single-LSP stdio pattern (initialize, didOpen, diagnostics). One server per process cannot be the broker |
| t3ta/mcp-language-server | MCP stdio. Fork of isaacphi with `config.json` listing several servers. Go binary | Yes (typescript, python, go, rust tested by upstream) | No (README prerequisites only) | Closest multi-server shape. Pre-beta. No seat split, no registry install, would import a Go tree |
| beruang/lsp-mcp | MCP stdio (`node dist/index.js`). LSP children stdio, including TS/JS, Python, Go | Yes | No (binaries must already be on `PATH`) | Useful per-language pool idea. 59 tools and a single combined process. Adopting it would be a wholesale import |
| code-yeongyu/lsp-tools-mcp | stdio MCP (`node dist/cli.js mcp`) | Config map | No | Tool names `lsp_status` / `lsp_diagnostics` are the naming pattern used here. Tied to Codex/OpenCode config paths, not a lifecycle daemon |

None of the four is network-primary-only. That class of transport is rejected anyway: WebSocket and HTTP are not the agent surface. Patterns actually used:

- stdio LSP Content-Length framing, `initialize` / `initialized` / `didOpen`, `textDocument/publishDiagnostics` (isaacphi / t3ta)
- one session per language id so a dead session does not stop the others (t3ta / beruang)
- MCP tool names `lsp_status` and `lsp_diagnostics`, plus spike tools `lsp_install`, `lsp_hover`, `lsp_definition` (hover and definition are stubs)
- registry entry + install into a state-dir prefix, in the spirit of mason.nvim, without vendoring upstream servers

## n7 — Workflow units on this branch

| Unit | Seat | This PR |
|---|---|---|
| A | INFRA | Broker, registry, fixture server, spike proof |
| B | WEB | `mcp-unified-lsp` stdio adapter and its proof |
| C | LEAD | This note and `.receipts/bot-00-programming-lead/unified-lsp-tier1-ut-tlvsqj-b31b8fe2.json` |
| D | QUALITY | **Not done.** Sandbox review (n6, SPE-167) trails the draft and blocks calling the spike done |
| E | recorded here | Greenfield, adapt patterns, reject network-primary transports |

Dispatch order followed: A/B/E plus LEAD notes. D is held.

## Ownership blocker (G-1 on this branch)

CI takes the acting bot from the branch prefix `bot-00-programming-lead/…` and then requires every changed path to belong to that bot. This PR also changes `infra/**` (bot-05) and `web/**` (bot-02), so G-1 **as bot-00 against the whole diff fails**. That failure is the cross-seat fact, not a mis-filed path.

Checked the other way: each file passes G-1 when `--bot` is the owner from `ownership.yaml`. Seat-scoped branches, or a QUALITY waiver, would be required before this can merge. This PR stays draft. No ownership.yaml edit. No Greptile score. No merge claim.

## Hold

- Unit D sandbox: child filesystem/network policy, diagnostics exfiltration, install supply chain, WebSocket expansion. Partial scrub of child env and workspace-relative paths are in the broker and are not a QUALITY sign-off.
- Real `typescript-language-server`, `pyright-langserver`, and `gopls` diagnostics.
- Multi-language registry past Tier-1.
- Publishing `mcp-unified-lsp`.
- New Linear or Notion rows (density is already 7 + 37).
