# INFRA — Phase A half: substrate env placement + lease/drift install stubs

- **Run:** `20260930T065532Z-29e26e2b` · **Tickets:** SPE-4789, SPE-4793 (env placement, docs), SPE-4792 (lease heartbeat / drift_scan support)
- **Branch:** `claude/substrate-env-lease-stubs-1s6sf0` · **PR:** #36 (draft, hold)
- **Approved by:** *null until QUALITY*
- **Status:** docs and stubs. **Nothing installed, nothing restarted, no live env file edited.**

## What landed

**SPE-4789 / SPE-4793 — `infra/substrate/`**
`SUBSTRATE-ENV.md` is the placement contract for `/etc/substrate/substrate.env`; `substrate.env.example`
is the names-only template. `GREPTIME_URL`, `GREPTIME_USER`, `GREPTIME_PASSWORD`, `GREPTIME_DB` with the
preference order written down: the Ultrathink Tailscale forwarder MagicDNS name on `:4000` once live,
public HTTPS + Basic as the **current stable fallback** and what is on the VPS today. OTEL,
MCP-audit and evidence variables are reserved as **names only** for the cutover. Prior INFRA
receipts (`infra-spe4789-greptime-place-env`, `infra-spe4789-agent-events-append-mode`) are cited by
name; none of their output is restated or paraphrased as a result here.

`infra/desk-gateway/gateway.env.example` now marks its `GREPTIME_*` block **TRANSITIONAL**:
`substrate-mcp` owns the store credential long-term and the gateway reaches the plane over loopback.
One credential in two files is two files to rotate.

**SPE-4792 — `infra/lease-heartbeat/`**
`desk-lease-heartbeat.service` (`Type=oneshot`) + `.timer` (`OnUnitActiveSec`), a cron sketch with
`flock -n` for a host without systemd, `lease-heartbeat.env.example` (names only), and the cadence
invariant `LEASE_TIMEOUT_S < LEASE_INTERVAL_S <= LEASE_TTL_S / 3` to be enforced at install time.
`drift-probe.sh` is read-only and credential-free: git tip facts and bounded TCP reachability.
`DRIFT-SCAN.md` states the interface preference — `coord.drift_scan(repo)` called by seats, INFRA a
data source behind it — and the boundary: INFRA asserts reachability and the tip, **never**
`agent_events` rows, claim contents or claim CAS.

## Boundaries honoured

`services/**` untouched. No MCP server registered for Greptime. `DESK_GATE_USER` not enabled.
No `contracts/` edit. `ownership.yaml` not edited (it is QUALITY's) — which is why the two prose
files are `SUBSTRATE-ENV.md` and `LEASE-HEARTBEAT.md`: the manifest's bare `README.md` rule matches
at any depth and would send a README here to QUALITY. No values, no public domain, no token.

## For QUALITY / LEAD

Two things need a decision from someone else before this can go further:

1. **Branch naming.** Quality Gates derives the acting bot from the branch prefix
   (`^bot-0[0-6]-[a-z0-9-]+$`). This run was dispatched onto a `claude/` branch, so the gates job
   fails at that step before any gate runs. A `bot-05-infrastructure/` branch is needed for a green
   run; INFRA will not re-target without being told to.
2. **`ownership.yaml`.** An `infra/substrate/**` and `infra/lease-heartbeat/**` rule after the bare
   `README.md` line — the shape `infra/railway/**` already has — would let these directories carry
   ordinary READMEs. QUALITY's call.

Open on SYSTEMS: `LEASE_TTL_S` / `LEASE_INTERVAL_S` values, the `renew` exit-code contract, and
whether `coord.drift_scan` wants the raw snapshot or a reduced verdict (`DRIFT-SCAN.md` §5).
