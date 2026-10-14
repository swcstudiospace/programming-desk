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
| `anchor-proofs.env.example` | Variable names the unit may read. No values |

The service has no `[Install]` section. `systemctl enable` applies to the
timer. Enabling the service as well would also start a boot-time oneshot.

## What the oneshot runs

`ExecStart=/opt/programming-desk/infra/telemetry/verify-anchor-proofs.sh`

That is the canonical checkout path used by
[`../desk-gateway/desk-gateway.service`](../desk-gateway/desk-gateway.service).
`WorkingDirectory=/opt/programming-desk`. The script does not read the working
directory; the unit sets it so a relative path in a later change still starts
from the checkout.

The script reads these variables (defaults are in the script, not secrets):

| Name | Script default | Hourly unit |
|---|---|---|
| `GREPTIME_HTTP_URL` | `http://127.0.0.1:4000` | unset unless `anchor.env` sets it |
| `SOLANA_DEVNET_RPC` | `https://api.devnet.solana.com` | unset unless `anchor.env` sets it |
| `DRY_RUN` | `false` | leave unset. `true` skips the network |
| `REPORT_OUTPUT_DIR` | `/tmp/desk-anchors` | `/var/lib/desk-anchor-proofs` |

`PrivateTmp=true` would delete a report written under `/tmp` when the oneshot
stops. `StateDirectory=desk-anchor-proofs` creates
`/var/lib/desk-anchor-proofs` and `Environment=REPORT_OUTPUT_DIR=` points the
script there. `EnvironmentFile=` overrides that when the live file sets the
same name.

`EnvironmentFile=-/etc/desk-anchor-proofs/anchor.env` uses the `-` prefix, same
as `desk-gateway.service`. A missing file is not a failure: the script already
has defaults, and the report directory is set on the unit. Create the file
only to override. Do not put secrets in the unit. The live file stays
`root:root` `0600` and is never committed.

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

A non-zero exit from the script fails the oneshot. The script exits 1 when it
checked at least one batch and a batch failed. A query that returns no batches
exits 0; that behavior is in the script and this unit does not change it.

## Install and enable

Do not run this from a pull request. After the checkout at
`/opt/programming-desk` contains these files, and after a separate approval:

```bash
install -d -m 0700 /etc/desk-anchor-proofs
install -m 0600 -o root -g root \
  /opt/programming-desk/infra/telemetry/anchor-proofs.env.example \
  /etc/desk-anchor-proofs/anchor.env
# Edit /etc/desk-anchor-proofs/anchor.env if a default must change.
# Then remove the leading '#' on the lines you set. Do not commit that file.

install -m 0644 \
  /opt/programming-desk/infra/telemetry/verify-anchor-proofs.service \
  /etc/systemd/system/verify-anchor-proofs.service
install -m 0644 \
  /opt/programming-desk/infra/telemetry/verify-anchor-proofs.timer \
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
