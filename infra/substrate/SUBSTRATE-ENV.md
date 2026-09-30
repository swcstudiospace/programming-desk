# `/etc/substrate/substrate.env` — env name placement (INFRA)

**Owner:** INFRA (`bot-05-infrastructure`). **Tickets:** SPE-4789 (docs/receipts), SPE-4793 (env name
placement), with the cutover context in [`../../docs/upgrade-plan-desk-v2.md`](../../docs/upgrade-plan-desk-v2.md) §5–§6.

> Not named `README.md` on purpose: `ownership.yaml` carries a bare `README.md` pattern that
> matches at any depth, so a README here would resolve to QUALITY rather than INFRA. Either
> QUALITY adds `infra/substrate/**` and `infra/lease-heartbeat/**` after that rule (the shape
> `infra/railway/**` already has), or these files keep their explicit names. G-1 decides, not
> preference.

This directory documents **which variable names live in which file on the VPS**, and nothing else.
No values, no hosts with credentials in them, no probe transcripts. The live file is
`/etc/substrate/substrate.env`, root-owned `0600`, never committed. The committed artefact is
[`substrate.env.example`](./substrate.env.example): names and comments only.

---

## 1. Why the substrate holds these names and the gateway does not

`substrate-mcp` is the only process that talks to the data planes. The desk gateway reaches those
planes *through* the substrate over loopback (`SUBSTRATE_URL=http://127.0.0.1:7410`), so it needs
its own bearer and nothing else (plan §5 bullet 3).

| Variable family | Long-term home | Read by |
|---|---|---|
| `GREPTIME_*` | `/etc/substrate/substrate.env` | `substrate-mcp` |
| `SUBSTRATE_PG_URL`, `DRAGONFLY_URL` | `/etc/substrate/substrate.env` | `substrate-mcp` |
| `HINDSIGHT_*`, `RAGFLOW_*` | `/etc/substrate/substrate.env` | `substrate-mcp` |
| `SUBSTRATE_URL`, `SUBSTRATE_TOKEN` | `/etc/desk-gateway/gateway.env` | `desk-gateway` |
| Platform API tokens (Railway, Vercel, Play, ASC, Greptile, GitHub) | `/etc/desk-gateway/gateway.env` | `desk-gateway` |

`infra/desk-gateway/gateway.env.example` still lists `GREPTIME_*` so an operator can run the
gateway against the events plane directly while the substrate route is being brought up. That is a
**transitional** listing, marked as such in that file: once `events_emit` goes through the
substrate, the gateway's copy is emptied rather than kept in sync. Two files holding the same store
credential means two files to rotate, and the one nobody remembers is the one that leaks.

**A Bot never sees any of these.** They are not in `.mcp.json`, not in a template, not in a prompt.

---

## 2. `GREPTIME_*` — the four names

| Name | What it is | Notes |
|---|---|---|
| `GREPTIME_URL` | Base URL of the events plane | Scheme matters: see §3 |
| `GREPTIME_USER` | Basic-auth username | Required on the public route; harmless on the tailnet route |
| `GREPTIME_PASSWORD` | Basic-auth password | Never in this repo, never in a receipt, never in a PR body |
| `GREPTIME_DB` | Database name | `public` unless a migration says otherwise |

The events plane is the append-only `agent_events` table (plan §6): every gateway tool call, receipt
written, dispatch, intake and seat heartbeat, with a `hash`/`prev` chain. Appends only — a writer
that updates a row has the wrong access pattern, and SPE-4789's append-mode receipt is the record
of that being settled.

## 3. `GREPTIME_URL` — preference order

**Preferred, once the forwarder is live:** the Tailscale MagicDNS name for the Ultrathink
forwarder, plain HTTP on the mapped port —

```
GREPTIME_URL=http://ultrathink-production-tailscale-forwarder:4000
```

Plaintext is acceptable on that hop because the tailnet hop is WireGuard-encrypted (plan §5), and
the mapping is the one declared in [`../railway/forwarders.yaml`](../railway/forwarders.yaml)
(`4000` HTTP/SQL, `4001` gRPC, `4003` Postgres wire). Never a `*.railway.internal` name: Railway's
private network is per project and per environment and does not resolve from the VPS.

**Current stable fallback:** the public Railway domain over HTTPS with Basic auth —

```
GREPTIME_URL=https://<greptime-public-railway-domain>
GREPTIME_USER=<name only — value stays on the VPS>
GREPTIME_PASSWORD=<name only — value stays on the VPS>
```

This is what is placed on the VPS today. The private tailnet route is reachable from the VPS, but
pointing `substrate-mcp` at it produced a **startup timeout**, so the public HTTPS route remains the
configured value until that is resolved. The two INFRA receipts that record this — conceptually,
without repeating their output here — are:

- `infra-spe4789-greptime-place-env` — the placement of `GREPTIME_*` under `/etc/substrate/`,
  including the fallback decision.
- `infra-spe4789-agent-events-append-mode` — `agent_events` append-only write mode.

Neither is restated or paraphrased as a result in this document. If you need the probe exit codes,
read the receipts; this file is the placement contract, not the evidence.

**Switching to the tailnet route** is the plan §5 / `railway-tailscale` cutover, in that order:
probe first, edit `substrate.env` second, restart `substrate-mcp` third, verify fourth, and only
then retire public exposure under G-6 with a recorded `approval_id` and a rollback plan. Keep a
dated copy of `substrate.env` beside it before editing; that copy **is** the rollback.

Do **not** register a Greptime MCP server for this. The events plane is reached by `substrate-mcp`,
and a second client with its own copy of the credential is a second thing to rotate.

---

## 4. Substrate cutover placeholders — OTEL, MCP audit, evidence

Names reserved now so the cutover edits a file that already has the slots, and so a reviewer can
tell a missing variable from a variable nobody has thought about yet. **Names only** — every one of
these is empty in [`substrate.env.example`](./substrate.env.example), and an empty value means the
feature is off rather than misconfigured.

### 4.1 OTEL (traces/metrics/logs out of `substrate-mcp`)

Standard OpenTelemetry SDK names, so no bespoke mapping layer is needed:

`OTEL_SDK_DISABLED`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`,
`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_EXPORTER_OTLP_HEADERS`,
`OTEL_TRACES_SAMPLER`, `OTEL_TRACES_SAMPLER_ARG`, `OTEL_METRICS_EXPORTER`, `OTEL_LOGS_EXPORTER`.

`OTEL_EXPORTER_OTLP_HEADERS` carries a credential when the collector authenticates, so it obeys the
same rule as `GREPTIME_PASSWORD`: value on the VPS only. Prefer a tailnet collector endpoint for
the same reason `GREPTIME_URL` prefers one.

### 4.2 MCP audit (per-call record into the events plane)

`MCP_AUDIT_ENABLED`, `MCP_AUDIT_SINK`, `MCP_AUDIT_TABLE`, `MCP_AUDIT_ARGS_MODE`,
`MCP_AUDIT_REDACT`, `MCP_AUDIT_SAMPLE_RATE`, `MCP_AUDIT_QUEUE_MAX`, `MCP_AUDIT_FLUSH_INTERVAL_S`.

`MCP_AUDIT_ARGS_MODE` exists so the default can be a **hash** of the arguments rather than the
arguments: plan §7 records a redacted args hash, not the payload. `MCP_AUDIT_REDACT` is the
belt-and-braces switch for the redactor in front of the sink. The audit record is what makes a
refusal reviewable, so `MCP_AUDIT_ENABLED` empty/off is a deliberate operator choice, not a default
anyone should inherit silently.

### 4.3 Evidence (receipts, anchoring, retention)

`EVIDENCE_DIR`, `EVIDENCE_RECEIPTS_DIR`, `EVIDENCE_RETENTION_DAYS`, `EVIDENCE_ANCHOR_ENABLED`,
`EVIDENCE_ANCHOR_INTERVAL_S`, `EVIDENCE_ANCHOR_CHAIN`, `EVIDENCE_ANCHOR_RPC_URL`,
`EVIDENCE_ANCHOR_KEY_PATH`.

`EVIDENCE_ANCHOR_*` covers the hourly Merkle root anchoring described in plan §6.
`EVIDENCE_ANCHOR_KEY_PATH` is a **path**, not a key: a signing key never becomes an environment
value, because environment values end up in `systemctl show`, in crash dumps and in process
listings.

---

## 5. Editing the live file

1. `cp -a /etc/substrate/substrate.env /etc/substrate/substrate.env.$(date -u +%Y%m%dT%H%M%SZ)` —
   the rollback.
2. Edit; keep mode `0600` and owner `root:root`.
3. `systemctl restart substrate-mcp`; confirm the unit is active.
4. Re-run the service-level checks (`desk_db_health`, an `events_emit`, `desk_brief`). A probe that
   was not run is recorded as `unverified` in the receipt, not omitted.
5. The receipt records the diff **by variable name only**. G-3 flags a value; a reviewer flags a
   hostname-with-credential; neither belongs in a receipt anyway.
