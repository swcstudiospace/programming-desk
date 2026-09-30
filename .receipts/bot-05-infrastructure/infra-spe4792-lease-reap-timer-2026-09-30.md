# INFRA — SPE-4792 lease reap sweeper (timer + unit + wrapper)

- **Ticket:** SPE-4792 · **PR:** #38 (draft, hold) · **Branch:** `bot-05-infrastructure/substrate-env-lease-stubs-1s6sf0`
- **Approved by:** *null until QUALITY Path B*
- **Status:** **stub — not installed, never executed against a live `substrate-mcp`.**
- **Machine-readable evidence:** `infra-phase-a-substrate-env-lease-stubs-2026-09-30.json`
  (this change's commands and claims live there; this file is the prose companion for the
  sweeper half, which QUALITY noted was missing).

## What the sweeper is

One periodic call to the SYSTEMS-owned `coord_reap_leases` tool on the **loopback**
`substrate-mcp`, so a lease whose holder died is still released on a quiet desk.

| File | Role |
|---|---|
| `infra/lease-heartbeat/substrate-lease-reap.timer` | Cadence. Default **45s**, sanctioned band **30–60s** |
| `infra/lease-heartbeat/substrate-lease-reap.service` | `Type=oneshot`; `ExecStart` is the wrapper below |
| `infra/lease-heartbeat/substrate-lease-reap.sh` | Runs the call **and checks the result** |
| `infra/lease-heartbeat/smoke-reap-sse.sh` | Self-contained check for the multiline-SSE case: `bash infra/lease-heartbeat/smoke-reap-sse.sh` |

## The boundary INFRA does not cross

**INFRA schedules the call; it does not implement the reap.** Which lease is expired, and the
compare-and-set that releases it, stay behind the MCP tool next to the claim schema — a second
implementation of claim CAS is how one ticket gets claimed twice (`LEASE-HEARTBEAT.md` §1).

**On-demand reaping through the MCP tool is retained and stays SYSTEMS'.** This timer is a
sweeper for quiet load: a backstop for the case where nothing calls the tool for a while, never
the path the system relies on.

## Why there is a wrapper rather than a bare `curl`

`curl --fail-with-body` fails on a non-2xx status **and nothing else**, and MCP does not report
tool failures with a status code:

- a `tools/call` whose tool failed answers **HTTP 200** with `isError: true` inside `result`;
- a protocol-level failure answers **HTTP 200** with a JSON-RPC `error` member.

Both were exit 0 under the bare form, so systemd would have marked the sweep successful while
every expired lease stayed unreaped — a green timer over a job that is not running. Reproduced
and recorded in the JSON receipt: the old form exits **0** on an `isError` response, the wrapper
exits **5**.

Wrapper contract — exit non-zero unless the tool actually ran and actually succeeded:

| Exit | Meaning |
|---|---|
| 0 | Swept: HTTP 2xx, no JSON-RPC `error`, `result.isError` unset |
| 2 | HTTP status not 2xx |
| 3 | curl could not complete the request |
| 4 | Response not parseable as an MCP result |
| 5 | Tool reported failure (`error`, or `result.isError`) |

Exercised against a local fake MCP server in all seven response shapes (plain-JSON success,
`isError`, JSON-RPC `error`, SSE success, SSE `isError`, HTTP 500, unparseable body) plus an
unreachable endpoint and missing required env.

**SSE framing follows the spec, not the common case.** An event's data is *all* of its `data:`
lines joined with newlines, dispatched at the blank line that ends the event. Parsing each line
alone works only while the server emits compact one-line JSON — the moment it pretty-prints or
wraps a long result, every line is a fragment, the parse fails, and a healthy sweep is reported
failed on every tick. Covered: multiline success and `isError`, no space after the colon, no
trailing blank line, two events in one response, and a `[DONE]` sentinel.

**`SUBSTRATE_LEASE_REAP_LOG_BYTES` is validated as a non-negative integer** before any request.
Both `head -c "$N"` and the Python slice invert on a negative number — on a 10000-byte body
`head -c -2000` yields 8000 bytes, not 2000 — so one stray minus sign would have turned the
journal cap into "log almost everything", on exactly the failing ticks where payloads are
largest.

**The smoke check is discriminating, not decorative.** Run against the pre-fix wrapper from
`99028dd` it fails with exit 4 — the exact false-failure the finding described — and passes
against the fixed one. It starts a throwaway MCP on an ephemeral port, needs no external fixture,
no network and no secret, and can be re-run by anyone or by CI.

## Secrets

**None in the unit, none on a command line, none in this repo.** The bearer lives only in the
`root:root 0600` curl config file named by `SUBSTRATE_LEASE_REAP_CURL_CONFIG`; the wrapper never
reads or echoes it. A bearer on a command line is readable via `ps` and `systemctl show` by every
local user, which is why it is not an `Environment=` line either.

Failing response bodies *are* logged, bounded by `SUBSTRATE_LEASE_REAP_LOG_BYTES` — a failing
sweep is undiagnosable without them, and the request is a fixed no-argument tool call whose
response carries no credential of its own.

Env names added (values empty, names only): `SUBSTRATE_MCP_URL`,
`SUBSTRATE_LEASE_REAP_INTERVAL_SEC`, `SUBSTRATE_LEASE_REAP_TIMEOUT_SEC`,
`SUBSTRATE_LEASE_REAP_CURL_CONFIG`, `SUBSTRATE_LEASE_REAP_REQUEST`,
`SUBSTRATE_LEASE_REAP_LOG_BYTES`.

## Unverified

- **Nothing is installed and `coord_reap_leases` has never been called.** The tool name, its
  argument shape, and its response when there is nothing to reap are all assumptions; the fake
  server used in testing is INFRA's model of the protocol, not the real substrate.
- Whether a sweep with nothing to reap answers 2xx. INFRA assumes yes — if a "nothing to do"
  answered 4xx, the wrapper would fail the unit on every quiet tick. Open on SYSTEMS.
- The 45s default and the 30–60s band are reasoned, not measured against real lease churn.
- `substrate-lease-reap.sh` has been run only against a local fake server on loopback, never over
  a real MCP session with authentication.
