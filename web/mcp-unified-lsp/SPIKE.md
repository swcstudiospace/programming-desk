# mcp-unified-lsp (Tier-1 spike)

WEB-owned MCP stdio adapter (`bot-02-web-edge`). Package name `mcp-unified-lsp` is a working title and `private`: it is not an npm publish.

The adapter speaks newline-delimited JSON-RPC on stdin/stdout and forwards tools to the INFRA broker CLI. It does not listen on a port. Optional WebSocket, when enabled, stays inside the broker and is loopback-only.

An oversized `Content-Length` frame is rejected. Body discard starts after the header blank line (`\r\n\r\n` or `\n\n`), so extra header lines are not counted as body bytes, including when the blank line and body arrive in a later chunk. A finite body at the 1 MiB cap is still accepted when the header makes the buffered total larger; the adapter waits for the declared body instead of rejecting the partial chunk. A non-finite length (`NaN`, `Infinity`, or a digit string that becomes `Infinity`) drops one tainted newline message, including a `tools/call` that arrives after the header. The following newline-delimited request is handled again, and a finite `Content-Length` request still is too. A finite oversized body is discarded for its declared length. Bytes after that finite length still parse.

`lsp_status` calls the broker `health` subcommand. When the broker has not been started, or `state.json` says `stopped`, the tool result is that state with `isError` false. It does not surface `broker_not_running`.

Launch the broker, then the adapter, from the repo root. `ULSP_BROKER` and `ULSP_STATE_DIR` are required. Without them, tool calls return `broker_not_configured`.

```bash
mkdir -p /tmp/ulsp-state
python3 infra/unified-lsp-broker/broker.py --state-dir /tmp/ulsp-state start --workspace /path/to/workspace
```

In another shell, with that same state directory:

```bash
ULSP_BROKER=infra/unified-lsp-broker/broker.py \
ULSP_STATE_DIR=/tmp/ulsp-state \
ULSP_PYTHON=python3 \
node --experimental-strip-types web/mcp-unified-lsp/server.ts
```

The adapter reads newline-delimited JSON-RPC on stdin and writes responses on stdout. It does not listen on a port.

Run the adapter proof from the repo root (Node with type stripping):

```bash
node --experimental-strip-types web/mcp-unified-lsp/spike_proof.ts
```

The broker proof, including crash isolation and the WebSocket host check, is:

```bash
python3 infra/unified-lsp-broker/spike_proof.py
```
