# Seat lease heartbeats — INFRA install/env stubs (SPE-4792)

**Owner:** INFRA (`bot-05-infrastructure`). **Coordinating seat:** SYSTEMS (`bot-01-systems-backend`).
**Status:** stubs for review. **Nothing here is installed**, and there is deliberately no
`install.sh` — see §4.

> Not named `README.md` on purpose — see [`../substrate/SUBSTRATE-ENV.md`](../substrate/SUBSTRATE-ENV.md),
> first note: `ownership.yaml`'s bare `README.md` rule matches at any depth and resolves a README
> here to QUALITY.

A lease says "this seat is working on this, and will say so again within TTL seconds". The heartbeat
is what makes the lease decay on its own: a seat whose host died stops renewing, the lease expires,
and the claim becomes available without anyone having to notice the death. That is the whole point,
and it is why the cadence invariant in §3 is not a tuning preference.

---

## 1. The split — what INFRA owns and what it does not

| Concern | Owner | Why |
|---|---|---|
| Unit files, timer cadence, env file location and mode | **INFRA** | It is host wiring on an INFRA-owned VPS |
| Env **names** the unit reads | **INFRA** | Placement is the thing that goes wrong on a host |
| Env **values** for TTL/interval | SYSTEMS | They follow from the lease semantics, not the host |
| What a lease *is*; renew/expire/steal semantics | SYSTEMS | Coordination logic, `services/**` |
| **Claim CAS** — compare-and-set on an open claim | **SYSTEMS** | See the warning below |
| `coord.drift_scan(repo)` implementation | SYSTEMS | Seats call it; INFRA feeds it |
| Reachability + git-tip probe helpers | **INFRA** | [DRIFT-SCAN.md](./DRIFT-SCAN.md) |

> **INFRA does not implement claim CAS.** The heartbeat renews a lease this host already holds and
> reports when it can no longer renew. It never takes a lease from another holder. A compare-and-set
> on a claim is a correctness-critical write against the index plane, it belongs next to the claim
> schema, and two implementations of it — one in a shell timer, one in the service — is the exact
> shape of a double-claimed ticket. If this unit ever needs to acquire rather than renew, it calls
> SYSTEMS' endpoint to do it.

## 2. Files in this directory

| File | What it is |
|---|---|
| `desk-lease-heartbeat.service` | `Type=oneshot` renewal unit. **Stub**: `ExecStart` names a SYSTEMS entrypoint that does not exist yet |
| `desk-lease-heartbeat.timer` | `OnUnitActiveSec` timer driving the service. The literal interval is a placeholder, generated from `LEASE_INTERVAL_S` at install time |
| `substrate-lease-reap.service` | `Type=oneshot` **sweeper**: one call to the SYSTEMS-owned `coord_reap_leases` tool on the local substrate-mcp. **Stub** — see §6 |
| `substrate-lease-reap.timer` | Drives the sweeper. Default 45s, permitted 30–60s |
| `lease-heartbeat.env.example` | Every variable the unit reads, names only, all values empty |
| `drift-probe.sh` | Runnable, read-only, credential-free reachability + git-tip probe |
| `DRIFT-SCAN.md` | What INFRA feeds `coord.drift_scan(repo)` and what it refuses to assert |

Live env file: `/etc/desk-lease-heartbeat/heartbeat.env`, `root:root`, `0600`, never committed —
the same rule as `/etc/substrate/substrate.env` and `/etc/desk-gateway/gateway.env`. Placement
across all three files: [`../substrate/SUBSTRATE-ENV.md`](../substrate/SUBSTRATE-ENV.md) §1.

### Why a systemd timer and not a sleep loop

`Type=oneshot` + timer means the cadence lives outside the process. A daemon with `sleep
$LEASE_INTERVAL_S` inside it has one failure mode that matters: the loop stops — a wedged socket
read, a swallowed exception — while the process stays `active (running)`. systemd reports it
healthy, the lease quietly stops being renewed, and the first symptom is an expired claim nobody
can explain. With a timer, a wedged tick is killed by `TimeoutStartSec` and the next tick still
fires, and `systemctl list-timers` shows the last and next run as plain facts.

### Cron sketch, if the host has no systemd

Not equivalent, and the gaps are worth stating rather than discovering:

```cron
# /etc/cron.d/desk-lease-heartbeat — sketch. Requires LEASE_INTERVAL_S == 60 exactly.
# Cron has no EnvironmentFile, so the entrypoint reads it directly — see the warning below.
* * * * * root /usr/bin/flock -n /run/desk-lease-heartbeat.lock \
  desk-lease-heartbeat renew --env-file /etc/desk-lease-heartbeat/heartbeat.env \
  >> /var/log/desk-lease-heartbeat.log 2>&1
```

**`LEASE_INTERVAL_S == 60` exactly, not `>= 60`.** Cron's finest granularity is one minute, so a
sub-minute interval is not expressible — but the ceiling matters just as much: this line fires
every minute *whatever* the env file says, so a valid `LEASE_INTERVAL_S=120` renews twice as often
as configured. A cron host that needs any other interval needs a wrapper that tracks elapsed time
against `LEASE_STATE_DIR` and exits early when the tick is not due. The systemd path is the
supported one; this is a fallback with a single supported cadence.

**The entrypoint reads the env file; the wrapper must not source it.** An earlier version of this
sketch used `sh -c '. heartbeat.env && exec ...'`, which is wrong: sourcing *executes* the file as
shell, and systemd's `EnvironmentFile` format is not shell. A token containing `$`, a backtick or
a quote would be expanded, mangled or would abort the wrapper — so cron would renew with a
different credential, or fail, while the systemd unit on the next host read the same file
correctly. Hence `--env-file`, parsed by the entrypoint the way systemd parses it. This is the
one thing INFRA needs from SYSTEMS before the cron path is usable at all (§5).

`flock -n` is not optional either: without it a renewal that overruns a minute has two ticks
running against the same lease.

The env file's `0600` mode is the only thing keeping `LEASE_ENDPOINT_TOKEN` out of the log
directory, so redirect stdout carefully — and never add `set -x` to a wrapper around it.

## 3. Cadence invariant

```
LEASE_TIMEOUT_S   <   LEASE_INTERVAL_S
LEASE_INTERVAL_S  +   LEASE_JITTER_S   +   LEASE_TIMEOUT_S   <=   LEASE_TTL_S / 3
```

- **`INTERVAL + JITTER + TIMEOUT <= TTL/3`** so two consecutive missed renewals do not expire a
  live lease. One missed tick is a network blip; three is a dead holder. At `INTERVAL = TTL/2` a
  single slow tick plus one blip loses a lease the seat still holds, and the seat finds out by
  having its claim taken.

  **Every term is time that can pass between one renewal landing and the next**, which is why all
  three are inside the bound rather than added on top of it:

  | Term | Why it counts |
  |---|---|
  | `LEASE_INTERVAL_S` | the tick itself |
  | `LEASE_JITTER_S` | `RandomizedDelaySec` is added to *every* tick, not averaged away |
  | `LEASE_TIMEOUT_S` | **`OnUnitActiveSec` measures from when the previous renewal *started*, not when it finished.** So the next renewal's own runtime lands on top of the interval, and its worst case is the timeout |

  Drop any one of them and the worst-case gap between *completed* renewals exceeds a third of the
  TTL at the permitted boundary — the margin is gone before the renewal starts. The systemd
  measurement point is the subtle one: an interval "since the last run finished" would not need
  the `TIMEOUT` term, and that is not what `OnUnitActiveSec` does.
- **`TIMEOUT < INTERVAL`** so a hung renewal cannot eat the tick that would have recovered from it.
  This is implied by the bound above but stated separately because it is the one an operator
  tuning a single value is most likely to break.
- `LEASE_JITTER_S` exists because seven seats restarted together otherwise renew in lockstep
  forever, which turns one substrate hiccup into seven lost leases.

systemd cannot read any of these out of an `EnvironmentFile`, so **all three unit literals are
generated at install time**, never hand-maintained: `OnUnitActiveSec` from `LEASE_INTERVAL_S`,
`RandomizedDelaySec` from `LEASE_JITTER_S`, and `TimeoutStartSec` from `LEASE_TIMEOUT_S`. A
hand-edited unit and an env file disagreeing about the cadence is a TTL nobody can compute from
the repo — and a `TimeoutStartSec` left at a fixed literal silently breaks the `TIMEOUT < INTERVAL`
guarantee the moment SYSTEMS picks a shorter interval.

## 4. Why there is no `install.sh` yet

The `ExecStart` target (`services/desk-lease-heartbeat/`) is SYSTEMS-owned and does not exist. A
timer installed now would fail every tick, fill the journal, and train whoever reads
`systemctl --failed` to ignore this unit — so the first real renewal failure would also be ignored.

Install once SYSTEMS lands the entrypoint. At that point the installer, matching
[`../desk-gateway/install.sh`](../desk-gateway/install.sh) conventions, must:

1. Create `/etc/desk-lease-heartbeat/heartbeat.env` from `lease-heartbeat.env.example` **once**,
   `0600 root:root`, and never overwrite it — an installer that rewrites a live env file is an
   installer that drops the token on upgrade.
2. Refuse to proceed when **any** of these is empty, and refuse when either §3 inequality fails —
   including the jitter and timeout terms:

   | Group | Variables | Why a missing one is fatal |
   |---|---|---|
   | Cadence | `LEASE_TTL_S`, `LEASE_INTERVAL_S`, `LEASE_TIMEOUT_S`, `LEASE_JITTER_S` | Guessing a cadence means a lease expiring at a time nobody agreed to |
   | **Identity** | `LEASE_SEAT`, `LEASE_HOLDER_ID` | A renewal with no seat renews nothing while the unit reports success — a green timer over an expiring lease |
   | **Endpoint** | `LEASE_ENDPOINT_URL`, `LEASE_ENDPOINT_TOKEN` | Same failure, one step later: nowhere to send the renewal, or no right to make it |
   | State | `LEASE_STATE_DIR` | The drift probe reads the last-renewal timestamp from here |

   Cadence alone is not enough: the unit files now require the env file (no `-` prefix on
   `EnvironmentFile=`), so a *missing* file fails loudly — but a file that is present and half
   filled in is the case that still looks healthy, and only this check catches it.
3. Generate all three unit literals rather than shipping the placeholders: `OnUnitActiveSec` from
   `LEASE_INTERVAL_S`, `RandomizedDelaySec` from `LEASE_JITTER_S`, and `TimeoutStartSec` from
   `LEASE_TIMEOUT_S`. Leaving any of them at its literal is how the §3 guarantee quietly stops
   holding. Do **not** add `Persistent=` to the timer: it replays missed activations only for
   calendar timers, so on a monotonic timer it promises a catch-up tick that never arrives.
4. `mkdir -p /var/lib/desk-lease-heartbeat` (matching `ReadWritePaths=` in the unit) for
   `LEASE_STATE_DIR`.
5. `systemctl enable --now desk-lease-heartbeat.timer`, then verify with `systemctl list-timers`
   and one manual `systemctl start desk-lease-heartbeat.service` whose exit code goes in the
   receipt. Enabling the **timer**, not the service.
6. Record in the receipt: the unit files' checksums, `list-timers` output tail, the manual tick's
   exit code, and the env diff **by variable name only**.

## 5. What SYSTEMS needs from INFRA to close SPE-4792

- These env **names**, fixed, so the service can read them without a second naming round.
- The §3 invariant enforced at install time, so the service may assume it holds at runtime.
- `drift-probe.sh` as the reachability/tip input to `coord.drift_scan(repo)` — [DRIFT-SCAN.md](./DRIFT-SCAN.md).
- A `LEASE_ENDPOINT_TOKEN` minted per unit, not shared with the desk gateway.

What INFRA needs back, and is blocked on before this can be installed:

- The `services/desk-lease-heartbeat` entrypoint and its `renew` subcommand's exit-code contract
  (which exit codes mean "retry next tick" versus "lease lost, stop claiming it").
- A `--env-file` option on that entrypoint, parsing the file the way systemd's `EnvironmentFile`
  does. Without it the cron fallback has no safe way to load the env: sourcing it executes it as
  shell, which mangles any token containing `$`, a backtick or a quote (§2).
- Values for `LEASE_TTL_S`, `LEASE_INTERVAL_S` and `LEASE_JITTER_S`.
- Whether a lost lease should leave the timer running (INFRA's assumption: yes — it keeps trying
  and reports; stopping the timer means a recovered host never re-announces itself).

For the §6 sweeper specifically:

- Confirmation of the tool name `coord_reap_leases` and that it takes no arguments, plus whether a
  sweep with nothing to reap returns 2xx (INFRA's assumption: yes — `--fail-with-body` makes any
  non-2xx a unit failure, so a "nothing to do" that answered 4xx would page on every quiet tick).
- Whether a CLI entrypoint for it is coming; if so `ExecStart` becomes that command and both
  installer-written files in §6 disappear.
- The substrate bearer for this unit, minted separately from the heartbeat's and the gateway's.

## 6. The lease sweeper — `substrate-lease-reap.{service,timer}`

**Renewal keeps a lease alive; reaping releases one whose holder stopped renewing.** The heartbeat
above is the first half. This is the second: a periodic call to the SYSTEMS-owned
`coord_reap_leases` tool on the local `substrate-mcp`, so an expired lease is actually released
rather than merely being past its TTL.

> **On-demand reaping is retained and stays SYSTEMS'.** The MCP tool is the primary path: whatever
> asks for a claim reaps first, and under normal load nothing here ever has work to do. **This
> timer is a sweeper for quiet load** — the case where no seat calls the tool for a while and an
> expired lease would sit unreleased until someone happened to want it. It is a backstop, not a
> replacement, and it must never become the thing the system relies on.

**INFRA schedules the call; it does not implement the reap.** Which lease is expired, and the
compare-and-set that releases it, live behind that tool next to the claim schema — §1's rule, for
§1's reason. A sweeper that decided expiry for itself would be the second implementation of claim
CAS, which is how one ticket ends up claimed twice.

One sweeper **per host**, not per seat: the tool reaps every expired lease in one call, so seven
copies would be six identical no-ops.

### Cadence

Default **45s**, permitted **30–60s**, from `SUBSTRATE_LEASE_REAP_INTERVAL_SEC`. Unlike the
heartbeat's interval this is **not** bound to `LEASE_TTL_S`: the sweeper renews nothing, so a
missed tick delays a release rather than losing a lease. Past 60s an expired lease can sit long
enough that a seat waiting on the claim notices, which is the delay the sweeper exists to prevent.

### Why a wrapper, not a bare `curl`

`ExecStart` calls `substrate-lease-reap.sh` rather than `curl` directly, because
**`curl --fail-with-body` fails on a non-2xx status and nothing else, and MCP does not report tool
failures with a status code.** A `tools/call` whose tool failed answers **HTTP 200** with
`isError: true` inside `result`; a protocol-level failure answers 200 with a JSON-RPC `error`
member. Under a bare curl both are exit 0, so systemd marks the sweep successful while every
expired lease stays unreaped until something calls the tool on demand — a green timer over a job
that is not running, which is precisely the failure §2 and §4 are written to avoid.

The wrapper's contract is the opposite: **exit non-zero unless the tool actually ran and actually
succeeded.**

| Exit | Meaning |
|---|---|
| 0 | Swept: HTTP 2xx, no JSON-RPC `error`, `result.isError` not set |
| 2 | HTTP status was not 2xx |
| 3 | curl could not complete the request (connect, timeout, bad config) |
| 4 | The response could not be parsed as an MCP result |
| 5 | The tool reported failure — JSON-RPC `error`, or `result.isError` |

It understands both a plain JSON body and an SSE (`text/event-stream`) one, since streamable-HTTP
MCP may answer either way for the same call and a sweeper that understood only one would quietly
stop checking results the day the server changed framing.

Failing bodies are logged to the journal, bounded by `SUBSTRATE_LEASE_REAP_LOG_BYTES` — a failing
sweep is undiagnosable without them, and the request is a fixed no-argument tool call, so the body
carries no credential of its own. The bearer is still only ever in the curl config file; the
wrapper never reads or echoes it.

It also keeps the curl invocation out of a systemd command line, where `%` is special and
`--write-out '%{http_code}'` would need escaping.

Requires `curl` and `python3`, both already present on a host running `substrate-mcp`.

### The two files the installer writes, and why they are files

`ExecStart` carries **no secret**, and neither does any `Environment=` line. A bearer on a command
line is visible in `ps` and in `systemctl show` to every local user, so it goes in a file that only
root can read:

`/etc/desk-lease-heartbeat/reap.curlrc` — `root:root 0600`, named by
`SUBSTRATE_LEASE_REAP_CURL_CONFIG`:

```
# value filled by the installer from the substrate bearer minted for this unit; never committed
header = "Authorization: Bearer <token>"
```

`/etc/desk-lease-heartbeat/reap-request.json` — the JSON-RPC body, named by
`SUBSTRATE_LEASE_REAP_REQUEST`. It holds no credential, so it is an ordinary `0644` file:

```json
{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
 "params": {"name": "coord_reap_leases", "arguments": {}}}
```

It is a file rather than an inline `--data` argument for a duller reason too: systemd treats `%`
specially in `ExecStart` and does no shell quoting, so inline JSON is a quoting trap that only
shows up the first time an argument grows.

If SYSTEMS ships a CLI entrypoint for the tool, `ExecStart` becomes that command and both files go
away. The curl form is the documented equivalent, not a preference.

### Env names (names only, as everywhere)

`SUBSTRATE_MCP_URL` (loopback — `http://127.0.0.1:7410/mcp`; never a tailnet or public host, since
a sweeper able to reach another host's substrate is a sweeper able to reap another desk),
`SUBSTRATE_LEASE_REAP_INTERVAL_SEC`, `SUBSTRATE_LEASE_REAP_TIMEOUT_SEC`,
`SUBSTRATE_LEASE_REAP_CURL_CONFIG`, `SUBSTRATE_LEASE_REAP_REQUEST`.

The `_SEC` suffix matches the SPE-4792 ticket's spelling while the heartbeat above uses `_S`. Same
unit, two spellings, both deliberate — neither is a typo to fix in place.

### Install (same standing as §4: not yet)

`substrate-lease-reap` depends only on the `coord_reap_leases` tool existing on the local
substrate, so it can be installed **before** the heartbeat's `services/**` entrypoint lands. It
still is not installed here, and the same installer rules apply: write the env file once at
`0600`, generate `OnUnitActiveSec` from `SUBSTRATE_LEASE_REAP_INTERVAL_SEC` and `TimeoutStartSec`
from `SUBSTRATE_LEASE_REAP_TIMEOUT_SEC`, refuse an interval outside 30–60, `systemctl enable --now`
the **timer**, and put the manual tick's exit code in the receipt.

