# desk-lease-heartbeat

Service README for the oneshot that renews graph-node leases this desk already
holds (SPE-12499). The filename is `INTERFACE.md`, not `README.md`, because
`ownership.yaml`'s bare `README.md` rule resolves every README in the tree to
QUALITY. SYSTEMS owns this directory. INFRA writes the installer, the live env
file, and the units against the contract below, and does not need this process
to sleep: `desk-lease-heartbeat.timer` fires `desk-lease-heartbeat.service`
every 60s.

The renewal call is the substrate MCP tool `graph_heartbeat`. That is the same
call `desk_graph_state` action `heartbeat` (SPE-5715) and
`coordination_graph_heartbeat` already make. This process does not claim, steal,
release, or reap. Reaping stays on `coord_reap_leases` and
`substrate-lease-reap.*`.

## CLI

```text
desk-lease-heartbeat renew [--env-file PATH]
```

| Piece | Meaning |
|---|---|
| `renew` | One tick. Exit when the tick finishes. No sleep loop. |
| `--env-file PATH` | Parse `PATH` as a systemd `EnvironmentFile`. No shell expansion. Assignments in the file override the same keys in the process environment. The cron fallback in `infra/lease-heartbeat/LEASE-HEARTBEAT.md` depends on this flag. The systemd unit does not need it: `EnvironmentFile=` is already in the process environment. |

The console script is `desk-lease-heartbeat`. The oneshot the unit execs is that
script plus the `renew` subcommand. On the VPS the checkout is
`/opt/desk-gateway/programming-desk`, so the script the installer should exec is:

```text
/opt/desk-gateway/programming-desk/services/desk-lease-heartbeat/.venv/bin/desk-lease-heartbeat renew
```

The process does not embed that path. Build it from this directory:

```bash
cd /opt/desk-gateway/programming-desk/services/desk-lease-heartbeat
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/desk-lease-heartbeat renew
```

There are no third-party dependencies. The stub unit under `infra/lease-heartbeat/`
still names a different checkout prefix; INFRA owns that file and points the
installed unit at the path above.

## Exit codes

| Code | Meaning | Timer |
|---|---|---|
| 0 | Every held lease was renewed, or there was nothing to renew | Next tick as usual |
| 0 | Nothing held (`held.json` missing, empty, or only other seats) | Logged `nothing held` |
| 0 | Upstream not configured (URL or token empty) while leases are held | Logged `upstream not configured`. Renewals are skipped, not invented |
| 0 | Substrate answered `ok: false` (`lost`, `expired`, `unheld`, `not-holder`, or any other `ok: false`) | Those rows are removed from `held.json`. The timer keeps running. This is not a claim |
| 1 | Partial failure: at least one lease renewed and at least one hit a real error | Next tick retries the ones still in `held.json` |
| 2 | Upstream HTTP status was not 2xx (including 401) and nothing was renewed | Real failure |
| 3 | The request did not complete (connect, overall timeout, bad URL) and nothing was renewed | Real failure |
| 4 | The response was not a JSON-RPC result and nothing was renewed | Real failure |
| 5 | JSON-RPC `error` or `result.isError` and nothing was renewed | Real failure |
| 6 | Env file, cadence invariant, or `held.json` is malformed | Real failure. Fix the file; do not treat it as nothing held |

When every attempt fails and the failures are mixed, the code is the first match of: unreachable, then HTTP, then unparseable, then tool error.

A lost lease does not stop the timer. Stopping the timer would mean a recovered host never renews again. `LEASE_MAX_MISSED` consecutive real failures of one lease drop that row and still exit non-zero on that tick.

## Environment

INFRA writes `/etc/desk-lease-heartbeat/heartbeat.env` (root:root 0600, never
committed). `substrate-lease-reap` reads that same file. This service reads
only the names below. Unknown keys, including the reap and drift names, are
ignored. Names only in [`heartbeat.env.example`](heartbeat.env.example). Every
value empty. No tokens.

`heartbeat.env` needs these names for this service:

- `LEASE_SEAT`
- `LEASE_HOLDER_ID`
- `LEASE_ENDPOINT_URL`
- `LEASE_ENDPOINT_TOKEN`
- `LEASE_TTL_S`
- `LEASE_INTERVAL_S`
- `LEASE_JITTER_S`
- `LEASE_TIMEOUT_S`
- `LEASE_MAX_MISSED`
- `LEASE_STATE_DIR`
- `LEASE_HELD_FILE`
- `LEASE_LOG_LEVEL`
- `LEASE_LOG_BYTES`

| Variable | When empty |
|---|---|
| `LEASE_SEAT` | Rows are not filtered by seat. Logged on success when set |
| `LEASE_HOLDER_ID` | Omitted from the success line. Not sent to the substrate |
| `LEASE_ENDPOINT_URL` | With the token, both must be set once anything is held. Otherwise exit 0 and log `upstream not configured` |
| `LEASE_ENDPOINT_TOKEN` | Same. Never written to the journal, at any log level |
| `LEASE_TTL_S` | Omit `ttl_seconds` and let the substrate keep its default. Integer 30..86400 when set. Out of range is exit 6 |
| `LEASE_INTERVAL_S` | Skip the cadence check. The process does not sleep on it. Positive integer when set |
| `LEASE_JITTER_S` | Skip the cadence check. Integer >= 0 when set |
| `LEASE_TIMEOUT_S` | Overall budget for one `renew` is 10 seconds. Positive integer when set |
| `LEASE_MAX_MISSED` | A real failure never drops the row by count. Positive integer when set |
| `LEASE_STATE_DIR` | No held file means nothing held, exit 0 |
| `LEASE_HELD_FILE` | Use `$LEASE_STATE_DIR/held.json` |
| `LEASE_LOG_LEVEL` | `info`. Also `debug`, `warning`, `error` |
| `LEASE_LOG_BYTES` | 2000. Non-negative integer. A negative value is exit 6 |

### Overall timeout and the TTL

`LEASE_TIMEOUT_S` is the wall-clock budget for one `renew` run, not a fresh
budget per lease. The clock starts when the tick begins calling upstream.
Each `graph_heartbeat` gets only the time still left. A lease that would
start after the budget is already spent is an unreachable failure (`overall
timeout`) and is not sent. Exit 3 when nothing was renewed, exit 1 when an
earlier lease in the same tick was renewed.

That budget is the same number INFRA writes as the unit's `TimeoutStartSec`.
It has to fit the lease lifetime with the timer's interval and jitter:

```text
LEASE_TIMEOUT_S < LEASE_INTERVAL_S
LEASE_INTERVAL_S + LEASE_JITTER_S + LEASE_TIMEOUT_S <= LEASE_TTL_S / 3
```

The sum is the longest gap between two completed renewals: the tick itself,
the jitter systemd adds to every tick, and this run's own budget, because
`OnUnitActiveSec` measures from when the previous run started. Two missed
ticks then still leave a third of the TTL. When all four are set, this
process refuses the tick (exit 6) if either inequality fails. It does not
sleep for `LEASE_INTERVAL_S` or `LEASE_JITTER_S`; the timer owns those.

A 60s timer with 5s jitter and a 900s TTL leaves room for an overall timeout
up to 59s, because `60 + 5 + 59 = 124` and `900 / 3 = 300`. Ten seconds is
inside that margin.

The endpoint is substrate-mcp, loopback, the same JSON-RPC `tools/call` shape as `substrate-lease-reap.sh`. Tool name: `graph_heartbeat`. Arguments: `graph_id`, `node_id`, `lease_id`, and `ttl_seconds` when configured. A per-lease `ttl_seconds` in `held.json` wins over `LEASE_TTL_S`.

## held.json

`graph_get` does not return `lease_id`, including to the holder. The id is shown once, on the grant from `graph_claim`. Whoever claimed the node writes it here. This process only reads it and deletes a row it can no longer renew.

Path: `$LEASE_HELD_FILE` or `$LEASE_STATE_DIR/held.json`. Mode `0600` when this process rewrites it.

```json
{
  "leases": [
    {
      "graph_id": "ut-example-0123abcd",
      "node_id": "n1",
      "lease_id": "from-graph-claim",
      "seat": "bot-01-systems-backend",
      "ttl_seconds": 900
    }
  ]
}
```

A bare JSON list of the same objects is accepted. `graph_id` matches `ut-[a-z0-9]+-[0-9a-f]{8}`. `node_id` is `n1`..`n8`. `lease_id` is 1..200 characters on one line. `seat` and `ttl_seconds` are optional. A missing file is nothing held. A present file that does not match this shape is exit 6.

Other files in the state directory, written by this process:

| File | Contents |
|---|---|
| `misses.json` | Consecutive real failures per `graph_id/node_id`. No `lease_id` |
| `last-renewal` | Unix seconds of the last tick on which every lease we still claim was renewed. One line, mode `0644`, for the drift probe to read without a network call |

## Logging

Journal lines are `desk-lease-heartbeat: ...` on stderr. They name `graph_id` and `node_id`. They do not name `lease_id`, the bearer, or the `Authorization` header. A failing body is redacted and capped before it is copied. The logged URL is scheme, host, port, and path.

## Tests

```bash
python3 -m pytest services/desk-lease-heartbeat/tests -q
```

From this directory, `python3 -m pytest -q` collects the same tests. No extra packages: pytest is the runner the rest of the repo already uses. The gate workflow's `pytest ci/tests` command does not collect this tree; that workflow file is INFRA's, and `ci/tests/` is QUALITY's. Run the command above in the service's own job the same way `services/desk-gateway` runs its suite.
