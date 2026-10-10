# desk-gateway

One MCP endpoint per Programming Desk seat, served from the VPS. Grok Bot seats connect to
`https://desk.swcstudio.space/mcp/<seat>` through the "Add MCP Server" card; the gateway maps the
OAuth token to a seat, serves exactly that seat's tool roster from `contracts/tool-rosters/`, and
brokers every call to the data planes (Hindsight, RAGFlow, Greptime, Timescale, Dragonfly), the
substrate MCP, the agent bus and the platform APIs. Bots never join the tailnet and never hold an
upstream credential. Plan: `docs/upgrade-plan-desk-v2.md` §5–§10.

Owned by SYSTEMS (`bot-01-systems-backend`); the rosters it serves are owned by QUALITY.

## Endpoints

| Path | Auth | Purpose |
|---|---|---|
| `GET /health` | none | Version, seat endpoints, registered seats, intake queue counts, OAuth endpoints |
| `POST /mcp/<seat>` | seat token (scope `seat:<seat>`) | Streamable HTTP MCP for one seat: `lead systems web android ios infra quality` |
| `POST /mcp/<seat>/packs/<app>` | seat token | Pack-only surface for a seat with no `desk_app_tools_load` (WEB): `kanbanos desklanes clippyos` |
| `GET /.well-known/oauth-protected-resource/mcp/<seat>` | none | Protected-resource metadata per seat |
| `GET/POST /authorize`, `/token`, `/register` | — | OAuth AS (dynamic client registration, PKCE) |
| `GET/POST /oauth/consent` | — | Consent page; the seat passphrase entered here decides the seat scope |
| `POST /v1/intake` | origin token (`INTAKE_TOKENS`) | External asks for LEAD only; seat tokens get 403 |
| `POST /v1/quantum/qkd/bb84` | lead or systems | BB84. `bit_length` 0 returns aborted `insufficient_sample` and a null QBER |
| `POST /v1/quantum/qkd/e91` | lead or systems | E91 witness run. Not part of the drill's `all_passed` conjunction |
| `GET /v1/quantum/qkd/session/{session_id}` | any authenticated seat | Public counts and independently blinded per-node commitments. No key bytes. Aborted sessions stay aborted |
| `POST /v1/quantum/teleportation/ledger/snapshot` | lead or systems | Frozen prefix root and receipt ids |
| `GET /v1/quantum/teleportation/ledger/receipts` | any authenticated seat | Receipt list |
| `GET /v1/quantum/teleportation/ledger/receipt/{receipt_id}` | any authenticated seat | One receipt. Unknown is 404 |
| `GET /v1/quantum/teleportation/ledger/proof` | any authenticated seat | Inclusion proof for `receipt_id` and `tree_size` |
| `POST /v1/quantum/teleportation/ledger/proof/verify` | lead or systems | `valid` true or false. A bad shape is 400 |
| `POST /v1/quantum/teleportation/anchor/export` | lead or systems | One Memo (1232-byte payload, 400000 compute units, exact readback) or a prerequisite code. No second send. Unconfigured or unfunded is 503; a deadline is 504 and does not resend |
| `POST /v1/quantum/teleportation/drill/simulate` | lead or systems | Shared-runtime drill. `all_passed` is true only after a matching confirmed readback. A missing prerequisite, including an unfunded payer, keeps it false |

A token minted for one seat used against another seat's path is refused with HTTP 403
`{"error": "wrong_seat"}`. Unknown seats and packs are 404.

The `x-connector-key: <passphrase>` header is accepted as a bearer for smoke tests and for the
Grok Bot header-key connector mode; Bots should connect with OAuth.

## Tool surface

Rosters are loaded from `contracts/tool-rosters/*.yaml` at start (core eight + seat tools, 10–15
each) and packs from `contracts/tool-packs/*.yaml` (≤5 tools each, seat-restricted). The live
surface of a seat is its roster plus loaded packs, capped at 20; loading a pack that would exceed
the ceiling fails with `ceiling`.

Every call is validated against the roster's input schema (`additionalProperties: false`),
refused when an argument contains a credential shape (`secret_refused`), given a 20 s deadline,
and audited as a redacted `tool.call` event to `DATA_DIR/audit.jsonl` and the substrate `/events`.
Tools tagged `g5` require `rollback_plan` and `approval_id`; `g6` requires `approval_id`; both fail
closed when the upstream is not configured. Read tools fail open with `not_configured`.

## Configuration

All settings come from the environment; `main()` first loads `GATEWAY_ENV_FILE`
(default `/etc/desk-gateway/gateway.env`, template in `infra/desk-gateway/gateway.env.example`).

| Variable | Meaning |
|---|---|
| `HOST`, `PORT` | Listener, `127.0.0.1:8791` by default; nginx terminates TLS on `PUBLIC_HOST` |
| `DATA_DIR` | JSON store plus `quantum_teleportation.sqlite3` (directory 0700, file 0600). The anchored prefix is immutable; a later root does not erase a published Memo |
| `QUANTUM_NODE_ENDPOINTS` | JSON map of node id to base URL for teleport and repeater commands. Empty means no remote worker plane. QKD and the drill's key stages bind only in-process workers, which are a constructor test hook; without that binding those routes return 503 `worker_plane_unavailable` |
| `QUANTUM_NODE_TOKENS` | JSON map of node id to that worker's credential |
| `QUANTUM_NODE_LINKS` | JSON list of `[node, node]` pairs |
| `QUANTUM_SOLANA_RPC_URL` | HTTPS Devnet RPC with no userinfo or path. Empty leaves publication unconfigured |
| `QUANTUM_SOLANA_SIGNER_PATH` | Dedicated payer file. Settings does not open it. External funding was selected and is not observed; balance was 0 lamports at confirmed slot 509400169 on 2026-10-10. This is a trusted-device numerical simulator, not a hardware or device-independent system |
| `DESK_REPO_DIR` | programming-desk checkout; read with `git show`/`git archive`, never switched or pushed |
| `SEAT_PASSPHRASE_<SEAT>` | One distinct passphrase per seat; consent maps it to `seat:<seat>` |
| `INTAKE_TOKENS` | `origin:token,...` accepted on `/v1/intake` |
| `SUBSTRATE_URL/TOKEN`, `AGENT_BUS_URL/TOKEN` | Local upstreams on the VPS |
| `HINDSIGHT_URL/API_KEY`, `RAGFLOW_URL/API_KEY`, `GREPTIME_*`, `SUBSTRATE_PG_URL`, `DRAGONFLY_URL` | Data planes via the per-project Tailscale forwarders |
| `DRAGONFLY_CONNECT_TIMEOUT_MS` | Startup connect only. Default `500`. A seat request does not wait on this |
| `DRAGONFLY_COMMAND_TIMEOUT_MS` | Socket timeout and budget for one cache command. Default `250`. Rate-limit checks use `DRAGONFLY_RATE_LIMIT_BUDGET_MS` instead |
| `DRAGONFLY_RATE_LIMIT_BUDGET_MS` | Cap on one rate-limit check. Default `150`. The local token bucket answers when it expires |
| `DRAGONFLY_HEALTH_CHECK_INTERVAL_SEC` | Idle-connection check on the shared pool. Default `30`. `DRAGONFLY_SOCKET_KEEPALIVE` defaults on |
| `DRAGONFLY_BREAKER_FAILURES`, `DRAGONFLY_BREAKER_RECOVERY_SEC` | Shared circuit breaker. Defaults `3` failures and `30` seconds. While it is open, rate limits stay local and do no network I/O |
| `RAGFLOW_DATASETS` | Comma-separated dataset names to search. Unset means `programming-desk,agent-substrate`. A name RAGflow does not have is reported as missing and is not fatal |
| `RAGFLOW_DATASET_TTL_SEC` | How long a dataset name-to-id entry is reused. Default `600`. A miss or an unknown-dataset retrieval refreshes once |
| `DOCS_LOOKUP_BUDGET_SEC` | Cap on a RAGflow dataset lookup, including that one refresh. Default `4` |
| `DOCS_RETRIEVAL_BUDGET_SEC` | Cap on a RAGflow retrieval, including one retry after an unknown dataset. Default `10` |
| `RECALL_BANK_TIMEOUT_SEC` | Per-bank Hindsight recall budget. Default `6`. A slow bank is `timeout`; the others still return |
| `RAILWAY_*`, `VERCEL_*`, `GREPTILE_*`, `GITHUB_TOKEN`, `PLAY_ACCESS_TOKEN`, `ASC_*` | Seat platform tools |
| `PACK_<APP>_API_BASE` | Product API base per tool pack |

`DRAGONFLY_URL` unset leaves rate limits on the in-memory bucket. One process shares one pooled client. Startup connect and ping run outside the request budget, and a failed warm-up is retried in the background until the breaker opens. A seat request never waits on that connect. The token-bucket script is loaded once. Eight commands can be in flight; a ninth answers locally and does not open the breaker. `/health` stays `ok` when Dragonfly is down and reports `edge.limiter.mode` as `dragonfly`, `local`, or `breaker_open`.

## Run locally

```bash
cd services/desk-gateway
uv sync
python3 - <<'EOF'
from desk_gateway.server import generate_passphrases
for seat, value in generate_passphrases().items():
    print(f"SEAT_PASSPHRASE_{seat.upper()}={value}")
EOF
GATEWAY_ENV_FILE=./gateway.env DESK_REPO_DIR=../.. DATA_DIR=./.data uv run desk-gateway
curl -s http://127.0.0.1:8791/health
curl -s http://127.0.0.1:8791/mcp/ios -X POST \
  -H 'x-connector-key: <SEAT_PASSPHRASE_IOS>' \
  -H 'content-type: application/json' -H 'accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Deploy

`infra/desk-gateway/install.sh` creates `/etc/desk-gateway/gateway.env` from the template once,
runs `uv sync`, installs `desk-gateway.service` and restarts it. `install-nginx.sh` adds the
public vhost when DNS and certificates exist. Until then the service listens on loopback only.

## Tests

```bash
cd services/desk-gateway
uv sync
uv run pytest -q
```

`tests/test_server.py` runs the whole ASGI app in-process against the real contracts and a
throwaway git checkout: per-seat roster counts, cross-seat 403, OAuth DCR → PKCE → consent →
token → refresh, intake, packs and ceiling, `desk_doctor` register/check/install_prompt, and the
audit trail. No upstream is contacted; unconfigured upstreams must answer `not_configured`.
