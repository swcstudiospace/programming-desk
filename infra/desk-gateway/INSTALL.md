# desk-gateway VPS install

Run as root from a programming-desk checkout:

```bash
./infra/desk-gateway/install.sh
```

## Dependencies

| Tool | Notes |
|------|--------|
| `uv` | Expected at `/root/.local/bin/uv` |
| `systemd` | Unit `desk-gateway.service` |
| `curl` | Health probe after restart |
| `rsync` | **Required** to sync/prune `/opt/programming-desk` (`rsync -a --delete`). If missing, `install.sh` runs `apt-get install -y rsync`. |

Canonical checkout after install: `/opt/programming-desk`. Leave `DESK_GATE_USER` empty until a separate enablement ticket.

## Reload

`reload-nginx-gateway.sh` reloads one target. It does not search the process table.

| Variable | Default | Role |
|---|---|---|
| `DESK_SERVICE_UNIT` | `desk-gateway.service` | Unit passed to `systemctl reload-or-restart` when `systemctl` is on `PATH` |
| `SYSTEMCTL_BIN` | `systemctl` | systemctl binary. Tests point this at a recorder |
| `DESK_GATEWAY_PID_FILE` | unset | Used only when `systemctl` is absent. The file must contain one numeric PID in 1..4194303. SIGHUP uses an external `kill` when one is on `PATH`, and Bash's builtin otherwise |
| `DESK_RELOAD_NGINX` | `false` | Set to `true` or `1` to run `nginx -t` and reload nginx. Off unless passed explicitly |
| `NGINX_BIN` | `nginx` | nginx binary |
| `DESK_RELOAD_DRY_RUN` | `0` | Set to `1` to print each command and run none |

Dry-run:

```bash
DESK_RELOAD_DRY_RUN=1 DESK_RELOAD_NGINX=true ./infra/desk-gateway/reload-nginx-gateway.sh
```

`deploy-staging.sh` exports `DESK_RELOAD_NGINX` (default `false`) and does not reload nginx itself. Invoke the reload script with the flag set when a reload is intended. `SYSTEMCTL_BIN` selects the systemctl binary both scripts call.

## Release directory

Run the gateway from the release directory `deploy-staging.sh` publishes. The script copies the tree to `DESK_RELEASES_ROOT/<release-id>` (`DESK_RELEASES_ROOT` defaults to `/opt/programming-desk-releases`) and points `DESK_CURRENT_LINK` (default `/opt/programming-desk`) at that directory. Do not point the unit at a shared git checkout. Another agent switches that checkout between branches, and the running process follows the switch. Set `DESK_RELEASES_ROOT` to the parent directory; the script appends the release id.

Moving a host that still runs from a shared checkout is an operator step. It waits for a separate approval and is not performed by installing this script.
