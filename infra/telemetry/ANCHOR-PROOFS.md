# Hourly anchor-proof verification — systemd units (SPE-12502)

**Owner:** INFRA (`bot-05-infrastructure`).
**Status:** unit files only. **Nothing here is installed**, and there is no
`install.sh`. Enabling the timer on the VPS waits for a separate approval.

> Not named `README.md` on purpose. `ownership.yaml` matches a bare `README.md`
> at any depth and would hand that file to QUALITY. Same choice as
> [`../lease-heartbeat/LEASE-HEARTBEAT.md`](../lease-heartbeat/LEASE-HEARTBEAT.md).

There is no `REPO_MAP` in this repository. Infra units live next to the thing
they schedule: `infra/desk-gateway/desk-gateway.service`,
`infra/lease-heartbeat/*.timer`. The verifier is
[`verify-anchor-proofs.sh`](./verify-anchor-proofs.sh), so the timer lives here.

## Files

| File | What it is |
|---|---|
| `verify-anchor-proofs.service` | `Type=oneshot`. Runs the verifier once and exits |
| `verify-anchor-proofs.timer` | `OnCalendar=hourly`, `Persistent=true`, `RandomizedDelaySec=60` |
| `anchor-proofs.env.example` | `GREPTIME_HTTP_URL` only, with a placeholder value |

The service has no `[Install]` section. `systemctl enable` applies to the
timer. Enabling the service as well would also start a boot-time oneshot.

## What the oneshot runs

`ExecStart=/opt/desk-gateway/programming-desk/infra/telemetry/verify-anchor-proofs.sh`

`WorkingDirectory=/opt/desk-gateway/programming-desk`. The script does not read
the working directory; the unit sets it so a relative path in a later change
still starts from the checkout.

`EnvironmentFile=/etc/desk-anchor-proofs/anchor.env`. The live file is
root-owned, mode `0600`, and it is never committed. `GREPTIME_HTTP_URL` is its
only variable. Do not load `substrate.env`. The oneshot does not reference
that file. Solana RPC, dry-run, and the report directory stay on the script
defaults or on the unit. `Environment=REPORT_OUTPUT_DIR=/var/lib/desk-anchor-proofs`
is a unit setting, not a line in `anchor.env`.

`PrivateTmp=true` would delete a report written under `/tmp` when the oneshot
stops. `StateDirectory=desk-anchor-proofs` creates
`/var/lib/desk-anchor-proofs` and the unit's `Environment=` line points the
script there. A missing `anchor.env` fails the oneshot. Do not put secrets in
the unit.

Hardening on the service, matching the lease oneshots plus the gateway fields
this job needs: `User=root`, `Group=root`, `NoNewPrivileges=true`,
`PrivateTmp=true`, `ProtectSystem=strict`, `ProtectHome=true`. The job needs
the network (loopback Greptime and the devnet RPC), so `PrivateNetwork=` is
left at its default. `TimeoutStartSec=120` is well under the hour, so a hung
query cannot sit across the next tick.

## Timer

`OnCalendar=hourly` runs at minute 0 of every hour. `RandomizedDelaySec=60`
spreads that by up to one minute. `AccuracySec=1s` keeps systemd's own timer
accuracy from adding another minute on top. `Persistent=true` stores the last
run and fires once after boot if a tick was missed while the host was down.
That catch-up is why this is a calendar timer: `Persistent=` does not replay
`OnUnitActiveSec` timers (see the lease timers, which omit it for that reason).

A non-zero exit from the script fails the oneshot. Exit codes:

| Code | Meaning |
|---|---|
| 0 | Every checked batch verified |
| 1 | A checked batch failed, or the Greptime query failed |
| 2 | Usage error |
| 3 | Greptime returned no anchor batches in the window. The script logs `no anchor batches in window` |

Exit 3 is no data. It is not a verification failure. An empty window used to
exit 0; the hourly timer now shows that hour as failed so a quiet Greptime is
visible in the journal.

## Install and enable

Do not run this from a pull request. After the checkout at
`/opt/desk-gateway/programming-desk` contains these files, and after a separate
approval:

```bash
install -d -m 0700 -o root -g root /etc/desk-anchor-proofs
install -m 0600 -o root -g root \
  /opt/desk-gateway/programming-desk/infra/telemetry/anchor-proofs.env.example \
  /etc/desk-anchor-proofs/anchor.env
# Replace <greptime-http-url>. The live file stays root:root mode 0600.
# GREPTIME_HTTP_URL is its only variable. Do not load substrate.env.
# Do not commit the live file.

install -m 0644 \
  /opt/desk-gateway/programming-desk/infra/telemetry/verify-anchor-proofs.service \
  /etc/systemd/system/verify-anchor-proofs.service
install -m 0644 \
  /opt/desk-gateway/programming-desk/infra/telemetry/verify-anchor-proofs.timer \
  /etc/systemd/system/verify-anchor-proofs.timer

systemctl daemon-reload
systemctl enable --now verify-anchor-proofs.timer
systemctl list-timers verify-anchor-proofs.timer
```

The script's executable bit has to survive in the checkout. `ExecStart` does
not wrap it in a shell.

## Disable

```bash
systemctl disable --now verify-anchor-proofs.timer
rm -f /etc/systemd/system/verify-anchor-proofs.service \
      /etc/systemd/system/verify-anchor-proofs.timer
systemctl daemon-reload
```

Reports already written under `/var/lib/desk-anchor-proofs` stay until an
operator removes them. The timer does not write to Greptime or to Solana.
