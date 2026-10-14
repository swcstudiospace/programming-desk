# Seat lease heartbeats — INFRA units and installer (SPE-12501)

**Owner:** INFRA (`bot-05-infrastructure`). **Coordinating seat:** SYSTEMS (`bot-01-systems-backend`).
**Status:** unit files and `install.sh` are in the tree. The default installer writes or checks
files and does not enable timers. `--enable` is the only path that enables them. This change
does not run the installer on a host.
**Interface:** SYSTEMS `desk-lease-heartbeat renew` in
[PR #221](https://github.com/swcstudiospace/programming-desk/pull/221)
(`bot-01-systems-backend/spe-12499-desk-lease-heartbeat`,
`6ae2ea59f38d5c0b5cb83c5f98cd153dbae73340`, SPE-12499).

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
| `desk-lease-heartbeat.service` | `Type=oneshot`. `WorkingDirectory` and `ExecStart` use `/opt/desk-gateway/programming-desk`. `TimeoutStartSec=10` |
| `desk-lease-heartbeat.timer` | `OnUnitActiveSec=60`, `RandomizedDelaySec=5` |
| `substrate-lease-reap.service` | `Type=oneshot` sweeper. Same checkout for `WorkingDirectory` and `ExecStart` of `substrate-lease-reap.sh`. See §6 |
| `substrate-lease-reap.timer` | `OnUnitActiveSec=45`, `RandomizedDelaySec=5` |
| `heartbeat.env.example` | The 13 heartbeat names, values blank. `install.sh` copies this once |
| `lease-heartbeat.env.example` | Those names plus reap and drift names, values blank |
| `install.sh` | Writes or checks files. Enables timers only with `--enable` |
| `verify-units.sh` | `systemd-analyze verify` for every unit here, under a temporary root |
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
  /opt/desk-gateway/programming-desk/services/desk-lease-heartbeat/.venv/bin/desk-lease-heartbeat renew \
  --env-file /etc/desk-lease-heartbeat/heartbeat.env \
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

systemd cannot read any of these out of an `EnvironmentFile`. The shipped literals are the
cadence, and `install.sh` copies the unit files rather than rewriting them:

| Unit | Literal |
|---|---|
| `desk-lease-heartbeat.timer` `OnUnitActiveSec` | 60 |
| `desk-lease-heartbeat.timer` `RandomizedDelaySec` | 5 |
| `desk-lease-heartbeat.service` `TimeoutStartSec` | 10 |
| `substrate-lease-reap.timer` `OnUnitActiveSec` | 45 |
| `substrate-lease-reap.timer` `RandomizedDelaySec` | 5 |

Empty `LEASE_INTERVAL_S`, `LEASE_JITTER_S`, `LEASE_TIMEOUT_S`, and `LEASE_TTL_S` use 60, 5, 10,
and 900. A non-empty interval, jitter, or timeout must equal the heartbeat literal above, and the
two inequalities still have to hold. The reap interval is not part of that check: it does not
renew a lease. The installer prints names and these literals. It does not print env values.

## 4. Installer

`install.sh` is idempotent. By default it writes or checks files and does not call `systemctl`.
Enabling the timers requires `--enable`, which runs `systemctl enable` on the two timers and does
not start them. Do not pass `--enable` without an explicit yes to install on that host. A scratch
tree uses `--sysroot DIR` (absolute). The default sysroot is `/`, and that path requires root.
`--enable` is refused for any other sysroot.

```bash
infra/lease-heartbeat/install.sh [--sysroot DIR] [--enable]
```

1. Create `/etc/desk-lease-heartbeat/heartbeat.env` from `heartbeat.env.example` **once**, mode
   `0600`. When the process is root the owner is `root:root`. An existing file is never
   overwritten — an installer that rewrites a live env file is an installer that drops the token
   on upgrade. A later failed check does not roll the bytes back, and it does not replace them.
   Mode is set to `0600` without rewriting contents. Symlinks are refused.
2. Require these 13 names to be **present**. An empty value counts as present. The check does not
   print values.

   `LEASE_SEAT`, `LEASE_HOLDER_ID`, `LEASE_ENDPOINT_URL`, `LEASE_ENDPOINT_TOKEN`, `LEASE_TTL_S`,
   `LEASE_INTERVAL_S`, `LEASE_JITTER_S`, `LEASE_TIMEOUT_S`, `LEASE_MAX_MISSED`, `LEASE_STATE_DIR`,
   `LEASE_HELD_FILE`, `LEASE_LOG_LEVEL`, `LEASE_LOG_BYTES`.

   Reap and drift names from `lease-heartbeat.env.example` may share the file. This installer does
   not require them and will not rewrite the file to add them. Append them on the host before
   enabling the reap timer.
3. Pre-check §3. Empty cadence values use interval 60, jitter 5, timeout 10, TTL 900. A non-empty
   interval, jitter, or timeout must match the shipped heartbeat literal (60, 5, 10) because the
   units are copied, not generated. `Persistent=` stays absent.
4. Copy the four unit files to `/etc/systemd/system/` and create `/var/lib/desk-lease-heartbeat`
   (mode `0700`) for `ReadWritePaths=`. This happens only after the checks pass.
5. Stop. No `daemon-reload`, no enable, no start, unless `--enable` was passed.

`verify-units.sh` runs `systemd-analyze verify` on every `*.service` and `*.timer` in this
directory inside a temporary `--root`, with stub executables for `ExecStart`. It does not enable
units and it does not read the live env file.

## 5. What SYSTEMS needs from INFRA, and what PR #221 returns

- These env **names**, fixed, so the service can read them without a second naming round.
- The §3 invariant enforced at install time, so the service may assume it holds at runtime.
- `drift-probe.sh` as the reachability/tip input to `coord.drift_scan(repo)` — [DRIFT-SCAN.md](./DRIFT-SCAN.md).
- A `LEASE_ENDPOINT_TOKEN` minted per unit, not shared with the desk gateway.

PR #221 is the entrypoint this unit execs. `renew` is one tick. `--env-file` parses a systemd
`EnvironmentFile` with no shell expansion, which is what the cron sketch needs. Exit 0 covers a
renewed lease, nothing held, an unset upstream, and a substrate rejection that drops a row. Exits
1–5 are real failures the next tick retries. Exit 6 is a bad env, a failed cadence invariant, or a
malformed `held.json`. A lost lease does not stop the timer. The defaults this installer applies
when the four cadence keys are empty are interval 60, jitter 5, timeout 10, TTL 900
(`60 + 5 + 10 = 75`, `900 / 3 = 300`).

Still outside this change:

- Building the venv at the `ExecStart` path. That is a host install of the SYSTEMS package.
- Passing `--enable`. Timers stay disabled until that flag is used on a host.
- Minting `LEASE_ENDPOINT_TOKEN`. The installer never prints it.

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

**SSE framing follows the spec, not the common case.** An event's data is *all* of its `data:`
lines joined with newlines, dispatched at the blank line that ends the event; the optional single
space after the colon is framing, and `[DONE]` is skipped. Parsing each line on its own works only
while the server emits compact one-line JSON — the moment it pretty-prints or wraps a long result,
every line is a fragment, the parse fails, and a **healthy** sweep is reported failed on every
tick. That is the same "the timer says one thing, reality says another" failure as a missed error,
just inverted, so it is covered by tests: multiline success and `isError`, no space after the
colon, no trailing blank line, two events in one response, and a `[DONE]` sentinel.

**`SUBSTRATE_LEASE_REAP_LOG_BYTES` must be a non-negative integer**, and is validated before any
request is made. The cap is applied by `head -c "$N"` and by a Python slice, and **both invert on
a negative number** — on a 10000-byte body `head -c -2000` yields 8000 bytes, not 2000 — so one
stray minus sign would turn the journal cap into "log almost everything", on exactly the failing
ticks where payloads are largest. Empty means the default (2000); a negative or non-numeric value
is refused with exit 1 rather than clamped, because a clamp hides an env file that says something
the operator did not mean.

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

### Install

`install.sh` copies `substrate-lease-reap.service` and `substrate-lease-reap.timer` with the
shipped cadence: `OnUnitActiveSec=45`, `RandomizedDelaySec=5`, `TimeoutStartSec=30`. It does not
rewrite those literals and it does not enable the timer unless `--enable` is passed. The 45s
interval sits inside the 30–60s band above. The same env file rules as §4 apply: create
`heartbeat.env` once at mode `0600`, never overwrite it, and do not print values.

