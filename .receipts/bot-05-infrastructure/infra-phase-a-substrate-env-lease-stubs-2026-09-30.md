# INFRA — Phase A half: substrate env placement + lease/drift install stubs

- **Run:** `20260930T065532Z-29e26e2b` · **Tickets:** SPE-4789, SPE-4793 (env placement, docs), SPE-4792 (lease heartbeat / drift_scan support)
- **Branch:** `bot-05-infrastructure/substrate-env-lease-stubs-1s6sf0` (renamed from `claude/*` so G-1 can attribute the change) · **PR:** #38 (draft, hold) — supersedes #36, closed by the head-branch rename
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

## Second tip — five Greptile P1s, all real, all fixed

| Finding | Verdict | Fix |
|---|---|---|
| **4141814747** JSON receipt missing | **Correct, and my first claim that it was committed was wrong.** `.gitignore:5` is `.receipts/**/*.json`, so `git add` silently skipped it and the PR carried only the Markdown half | `git add -f`, the way the seat's existing `.json` receipts are tracked. `.gitignore` is unowned in `ownership.yaml`, so it was not edited |
| **4141814758** `ls-remote` can stall | Reproduced: a bare lookup against an unresponsive remote had to be killed by an outer cap (exit 124) | `DRIFT_GIT_TIMEOUT_S` + `GIT_TERMINAL_PROMPT=0` + ssh `BatchMode`. A timed-out lookup is a probe *result*: `note` says so, exit stays 0 |
| **4141814773** unchecked targets pass | Correct: empty `DRIFT_REACH_TARGETS` exited 0 with `"targets": []`, and a malformed target's failure was swallowed by `\|\| true` | Both now exit **3** with `ok: false`, plus `targets_requested` / `targets_malformed`. Well-formed targets beside a malformed one are still probed |
| **4141814794** `TimeoutStartSec` can exceed interval | Correct: a fixed `30` breaks `TIMEOUT < INTERVAL` as soon as SYSTEMS picks a shorter interval | Marked PLACEHOLDER, generated from `LEASE_TIMEOUT_S` at install time; added to the installer checklist |
| **4141814784** timer delay exceeds cadence | Correct: `RandomizedDelaySec` is added to every tick, so bounding `INTERVAL` alone puts the real gap past `TTL/3` at the permitted boundary | Invariant is now on the sum: `LEASE_INTERVAL_S + LEASE_JITTER_S <= LEASE_TTL_S / 3`. All three unit literals generated at install time |

Two of these (the stall and the empty-target case) were reproduced before being fixed, and both
reproductions are in the receipt with `expects_failure`.

## Third tip — a sixth P1, on the fix itself

**4141898005 — an unattempted git lookup reported success.** Correct, and worse than reported: on
the pushed tip an invalid `DRIFT_PROBE_TIMEOUT_S` also emitted `"timeout_s":abc` — **unparseable
JSON** — while still exiting 0.

Fixed at the root rather than at the call site. Both `*_TIMEOUT_S` values are validated before any
probe runs (seconds as a bare number, no unit suffix, greater than zero), and the script separates
**ran-and-failed** from **never-ran** everywhere: `timeout` exits 125/126/127 now mean the probe
was never attempted, so `ok` goes false and the exit is 3, while a deadline (124) stays a result
with exit 0. New fields: `remote_checked` on the tip probe, `targets_unattempted` beside
`targets_malformed` on the reachability probe.

**The same defect existed in the reachability probe and Greptile had not flagged it** — a probe
that could not start reported `"reachable": false` for every target, turning one typo in the env
file into "the whole substrate is down". Fixed in the same pass.

## Fourth tip — lease sweeper unit sketch (LEAD GO)

`substrate-lease-reap.service` (oneshot) + `.timer`: one periodic call to the SYSTEMS-owned
`coord_reap_leases` tool on the loopback `substrate-mcp`, so a dead holder's lease is still
released on a quiet desk. Default **45s**, sanctioned band **30–60s**.

**On-demand reaping through the MCP tool is retained and stays SYSTEMS'** — the timer is a sweeper
for quiet load, a backstop and not the path the system relies on. INFRA schedules the call and
does not implement the reap: expiry and the compare-and-set that releases a lease stay behind the
tool, next to the claim schema, for the §1 reason.

**No secret in either unit.** The bearer lives in a `root:root 0600` curl config file named by
`SUBSTRATE_LEASE_REAP_CURL_CONFIG`, never on a command line — a command line is readable in `ps`
and `systemctl show` by any local user. Env names added (values empty, as everywhere):
`SUBSTRATE_MCP_URL`, `SUBSTRATE_LEASE_REAP_INTERVAL_SEC`, `SUBSTRATE_LEASE_REAP_TIMEOUT_SEC`,
`SUBSTRATE_LEASE_REAP_CURL_CONFIG`, `SUBSTRATE_LEASE_REAP_REQUEST`.

Both units verify clean under `systemd-analyze`. Still not installed, and `coord_reap_leases` has
never been called — the tool name, its argument shape and its response when there is nothing to
reap are all open questions for SYSTEMS (§5).

## Fifth tip — eight more Greptile findings on #38, all real

| Finding | Verdict | Fix |
|---|---|---|
| **4141980702** P1 leading zeros break probe JSON | Correct. `05` and port `080` passed validation and emitted unquoted, and JSON forbids leading zeros — every probe could succeed while the snapshot stayed unparseable | Rejected, not normalised, for durations **and** ports (ports were the half not reported); port range enforced too |
| **4141980726** P1 empty targets pass validation | Correct. A trailing comma dropped a whole plane from the scan with `ok: true` | Split by hand: bash word-splitting *and* `read -ra` both discard a trailing empty field, so neither would have caught it. Empty entries now count as malformed |
| **4141980742** P1 heartbeat environment optional | Correct. `EnvironmentFile=-` let systemd renew with no seat, holder, endpoint or token — a green timer over an expiring lease | `-` dropped from both services; installer checklist now validates identity, endpoint and state, not just cadence |
| **4141980721** P1 timer understates renewal gaps | Correct, and it invalidated my own invariant. `OnUnitActiveSec` measures from renewal **start**, so the next renewal's runtime lands on top of the gap | Invariant is now `INTERVAL + JITTER + TIMEOUT <= TTL/3`, with a table saying why each term counts |
| **4141980755** P2 missed renewals not replayed | Correct. `Persistent=` applies to calendar timers only, so my comment promised a catch-up tick that never arrives | Removed from the heartbeat timer; the reap timer's comment corrected the same way |
| **4141980762** P2 cron ignores configured interval | Correct. The line fires every minute whatever the env says | Narrowed to `LEASE_INTERVAL_S == 60` exactly, with what a different cadence would require |
| **4141980775** P2 cron misreads environment values | Correct. `. file` *executes* it, and systemd's `EnvironmentFile` is not shell — a token with `$`, a backtick or a quote would be mangled | Sketch now passes `--env-file` to the entrypoint; the option is added to the §5 asks for SYSTEMS |
| **4141980782** P2 receipt cites superseded PR | Correct | Already fixed in `4e92549` before the finding arrived |

Two of these (leading-zero ports, and the reap timer's `Persistent` comment) were extensions of
the reported finding that Greptile had not flagged, fixed in the same pass.

## For QUALITY / LEAD

Two things need a decision from someone else before this can go further:

1. **Branch naming — resolved.** The head branch was renamed to
   `bot-05-infrastructure/substrate-env-lease-stubs-1s6sf0`, so the gates job's acting-bot step
   attributes the change instead of exiting before any gate runs. PR #36 kept, still draft.
2. **`ownership.yaml`.** An `infra/substrate/**` and `infra/lease-heartbeat/**` rule after the bare
   `README.md` line — the shape `infra/railway/**` already has — would let these directories carry
   ordinary READMEs. QUALITY's call.

Open on SYSTEMS: `LEASE_TTL_S` / `LEASE_INTERVAL_S` values, the `renew` exit-code contract, and
whether `coord.drift_scan` wants the raw snapshot or a reduced verdict (`DRIFT-SCAN.md` §5).
