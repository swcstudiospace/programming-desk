# INFRA — Phase A half: substrate env placement + lease/drift install stubs

- **Run:** `20260930T065532Z-29e26e2b` · **Tickets:** SPE-4789, SPE-4793 (env placement, docs), SPE-4792 (lease heartbeat / drift_scan support)
- **Branch:** `bot-05-infrastructure/substrate-env-lease-stubs-1s6sf0` (renamed from `claude/*` so G-1 can attribute the change) · **PR:** #36 (draft, hold)
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
