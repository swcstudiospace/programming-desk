# mcp-unified-lsp (Tier-1 spike)

WEB-owned MCP stdio adapter (`bot-02-web-edge`). Package name `mcp-unified-lsp` is a working title and `private`: it is not an npm publish.

The adapter speaks newline-delimited JSON-RPC on stdin/stdout and forwards tools to the INFRA broker CLI. It does not listen on a port. Optional WebSocket, when enabled, stays inside the broker and is loopback-only.

An oversized `Content-Length` frame is rejected. Body discard starts after the header blank line (`\r\n\r\n` or `\n\n`), so extra header lines are not counted as body bytes, including when the blank line and body arrive in a later chunk. A non-finite length (`NaN`, `Infinity`, or a digit string that becomes `Infinity`) drops one tainted newline message, including a `tools/call` that arrives after the header. The following newline-delimited request is handled again, and a finite `Content-Length` request still is too. A finite oversized body is discarded for its declared length. Bytes after that finite length still parse.

Run the adapter proof from the repo root (Node with type stripping):

```bash
node --experimental-strip-types web/mcp-unified-lsp/spike_proof.ts
```

The broker proof, including crash isolation and the WebSocket host check, is:

```bash
python3 infra/unified-lsp-broker/spike_proof.py
```
