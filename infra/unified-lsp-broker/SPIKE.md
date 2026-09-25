# Unified LSP broker (Tier-1 spike)

Box-local broker for graph `ut-tlvsqj-b31b8fe2`. Owned by INFRA (`bot-05-infrastructure`) because it lives under `infra/**`.

Run the proof from the repo root:

```bash
python3 infra/unified-lsp-broker/spike_proof.py
```

What it checks:

- Lifecycle: `cold` before start, `ready` after start, `serving` once a language session is up, `degraded` when one language server crashes, `stopped` after shutdown with no leftover server pids.
- Install-on-demand for registry ids `tsjs`, `python`, and `go`. A language outside that set (`rust`) returns `language_not_tier1` and is not installed.
- Diagnostics read for the fixture files under `fixtures/` (path ASSUMPTION for this spike).
- Optional WebSocket binds only on loopback and stays off unless `--ws` is set. `0.0.0.0` is refused. The handshake requires `Origin: http://{bound_host}:{port}` and header `X-ULSP-WS-Token`. A foreign or missing Origin is HTTP 403. A bad token after a matching Origin is HTTP 401. Frames larger than 65536 bytes are rejected. MCP does not use this socket.
- Production install plans for `typescript-language-server`, `pyright-langserver`, and `gopls` are reported and not executed.

The server that actually runs is `fixture_ls.py`, linked into the state directory on install. It is a stand-in, not the upstream language server.
