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
