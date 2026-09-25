# mcp-unified-lsp (Tier-1 spike)

WEB-owned MCP stdio adapter (`bot-02-web-edge`). Package name `mcp-unified-lsp` is a working title and `private`: it is not an npm publish.

The adapter speaks newline-delimited JSON-RPC on stdin/stdout and forwards tools to the INFRA broker CLI. It does not listen on a port. Optional WebSocket, when enabled, stays inside the broker and is loopback-only.

An oversized `Content-Length` frame is rejected and its declared body is discarded, including when the body arrives in a later chunk. A JSON line inside that body is not treated as a later request. Bytes after the declared length still parse.

Run the adapter proof from the repo root (Node with type stripping):

```bash
node --experimental-strip-types web/mcp-unified-lsp/spike_proof.ts
```

The broker proof, including crash isolation and the WebSocket host check, is:

```bash
python3 infra/unified-lsp-broker/spike_proof.py
```
