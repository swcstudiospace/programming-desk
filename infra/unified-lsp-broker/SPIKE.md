# Unified LSP broker (Tier-1 spike)

Box-local broker for graph `ut-tlvsqj-b31b8fe2`. Owned by INFRA (`bot-05-infrastructure`) because it lives under `infra/**`.

Run the proof from the repo root:

```bash
python3 infra/unified-lsp-broker/spike_proof.py
```

What it checks:

- Lifecycle: `cold` before start, `ready` after start, `serving` once a language session is up, `degraded` when one language server crashes, `stopped` after shutdown with no leftover server pids.
- Install-on-demand for registry ids `tsjs`, `python`, and `go`. A language outside that set (`rust`) returns `language_not_tier1` and is not installed.
- Diagnostics read for the fixture files under `fixtures/` (path ASSUMPTION for this spike). A result past 32 diagnostics, or past the JSON size cap, sets `truncated`. `diagnostics_total` is the language server's count, including items dropped for size. Files over 1048576 bytes return `file_too_large` with `limit_bytes`.
- `ULSP_LSP_TIMEOUT_S` is clamped so initialize plus the diagnostics wait fit in an 18s request budget, under the 20s RPC and MCP client deadlines. One deadline covers the whole diagnostics request, including a crash retry. `ULSP_REQUEST_BUDGET_S` may shorten that budget and is clamped to 18s. Non-finite values, including `NaN`, fall back to that 18s budget. If the budget is already spent when the per-language lock is acquired, the call returns `diagnostics_timeout` and leaves the running language server up. A timeout while that call is waiting on the language server still marks the session failed. With `ULSP_SPIKE_HOOKS=1`, a `spike_hold_s` file in the state directory holds the language lock after a successful diagnostics so a queued caller can hit that path.
- A second `start` takes an exclusive lock on `broker.lock` before it looks at `state.json` or unlinks `broker.sock`. A concurrent start, including one that arrives before `state.json` exists, returns `broker_already_running` and does not replace the live socket. A stopped or dead owner releases the lock and can be replaced. With `ULSP_SPIKE_HOOKS=1`, `ULSP_SPIKE_CLAIM_HOLD_S` pauses after that lock is held and before the socket is bound.
- Shutdown sets a stopping flag, stops accepting, and waits for in-flight diagnostics to finish the per-language lock before it kills language servers or writes `stopped`. A diagnostics call that has not entered that lock returns `broker_stopping`. The stopped record is not overwritten by a later diagnostics persist. `spike_hold_ready` appears while a test hold owns the language lock.
- Accepted unix and WebSocket clients get a read timeout (`ULSP_CLIENT_IDLE_S`, default 20s, capped at 20s) and a connection cap (`ULSP_MAX_CLIENTS`, default 32, capped at 64). An idle or incomplete handshake does not keep a thread forever, and a connection past the cap is closed without a new thread.
- A file that disappears or cannot be read between the existence check and the read returns `file_not_found` on the RPC response. The connection stays up.
- Optional WebSocket binds only on loopback and stays off unless `--ws` is set. `0.0.0.0` is refused. The handshake requires `Origin: http://{bound_host}:{port}` and header `X-ULSP-WS-Token`. A foreign or missing Origin is HTTP 403. A bad token after a matching Origin is HTTP 401. Frames larger than 65536 bytes are rejected. MCP does not use this socket. A browser `WebSocket` client cannot set `X-ULSP-WS-Token`. Browser presentation of the share token is outside this spike and is not implemented.
- Production install plans for `typescript-language-server`, `pyright-langserver`, and `gopls` are reported and not executed.

The server that actually runs is `fixture_ls.py`, linked into the state directory on install. It is a stand-in, not the upstream language server.
