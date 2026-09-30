# Railway over Tailscale — forwarder deployment (plan §5, node n2)

Railway's private network (`*.railway.internal`) is per project and per environment, so the VPS
needs one **Tailscale Forwarder** per project. After this, the VPS and the admin machines reach
every Railway data service by MagicDNS name and the public TCP proxies and domains are removed.

Owner: INFRA (`bot-05-infrastructure`). Machine-readable copy of the mappings: `forwarders.yaml`.

## 0. Confirm service names first (n1)

The service names below are assumed from defaults and the substrate env. Before setting any
mapping, list the services in each project and correct `forwarders.yaml` and this file if they
differ; a mapping to a wrong name fails silently (the forwarder starts, the port is dead).

```sh
railway service list --project <ultrathink-project-id>
railway service list --project <agent-substrate-project-id>
```

## 1. Tailscale auth key

Admin console → Settings → Keys → Generate auth key:

- Reusable: **on** (one key serves both forwarders)
- Ephemeral: **off** (an ephemeral node vanishes on redeploy and its name changes)
- Pre-approved: on, if device approval is enabled
- Tags: `tag:railway-forwarder`

`infra/tailscale/policy.hujson` must already be applied so the tag exists and its owner is
`autogroup:admin`. Store the key only in the Railway variable `TS_AUTHKEY`; never in this repo.

## 2. Deploy the forwarder into each project

Dashboard: open the project → **New → Template → "Tailscale Forwarder"** (Railway's own
template; it replaced the deprecated subnet-router template) → environment **production**.
Or from the CLI/MCP: `deploy-template` with the Tailscale Forwarder template id into the
project and environment. Then set the variables on the new service:

| Variable | Ultrathink / production | Agent Substrate / production |
|---|---|---|
| `TS_AUTHKEY` | the tagged reusable key | the same key |
| `CONNECTION_MAPPING_1` | `4000:greptimedb.railway.internal:4000` | `8888:hindsight-api.railway.internal:8888` |
| `CONNECTION_MAPPING_2` | `4001:greptimedb.railway.internal:4001` | `9380:ragflow.railway.internal:9380` |
| `CONNECTION_MAPPING_3` | `4003:greptimedb.railway.internal:4003` | `80:ragflow.railway.internal:80` |
| `CONNECTION_MAPPING_4` | `5432:timescaledb.railway.internal:5432` | — |
| `CONNECTION_MAPPING_5` | `6379:dragonfly.railway.internal:6379` | — |

Format is `<listen port>:<railway.internal host>:<target port>`. Greptime's three ports are
HTTP/SQL (4000), gRPC (4001) and Postgres wire (4003). RAGFlow port 80 is the web UI and is
optional; drop `CONNECTION_MAPPING_3` in Agent Substrate if browser access is not wanted.

**Volume.** The template needs a volume mounted at the tailscale state directory
(`/var/lib/tailscale` by default; confirm in the service's Volumes tab). Without it every
redeploy is a fresh machine: a new node, a new name suffix (`-1`, `-2`), and the old one lingers.

**Machine name.** Derived from `<project>-<environment>-<service>`, so expect
`ultrathink-production-tailscale-forwarder` and `agent-substrate-production-tailscale-forwarder`.
If a name comes out different (renamed service, name clash), rename the machine in the admin
console rather than changing every consumer.

**Disable key expiry.** Admin console → Machines → each forwarder → ⋯ → **Disable key expiry**.
Otherwise the node drops off after 180 days and the desk loses its databases.

## 3. Verify from the VPS

```sh
tailscale status | grep tailscale-forwarder            # both machines, both online
tailscale ping ultrathink-production-tailscale-forwarder
tailscale ping agent-substrate-production-tailscale-forwarder

curl -sf http://ultrathink-production-tailscale-forwarder:4000/health && echo greptime-http-ok
pg_isready -h ultrathink-production-tailscale-forwarder -p 4003     # Greptime PG wire
pg_isready -h ultrathink-production-tailscale-forwarder -p 5432     # Timescale
redis-cli -h ultrathink-production-tailscale-forwarder -p 6379 PING # NOAUTH also proves the hop
curl -sf http://agent-substrate-production-tailscale-forwarder:8888/health && echo hindsight-ok
curl -s -o /dev/null -w '%{http_code}\n' http://agent-substrate-production-tailscale-forwarder:9380/
```

Repeat the `tailscale ping` lines from the Mac mini (`tag:admin`). Any port that was not
exercised is recorded as `unverified` in the receipt, not omitted.

## 4. Cut the VPS over

Set the tailnet names in `/etc/substrate/substrate.env` and `/etc/desk-gateway/gateway.env`
(`GREPTIME_URL`, `SUBSTRATE_PG_URL`, `DRAGONFLY_URL`, `HINDSIGHT_URL`, `RAGFLOW_URL`), restart
`substrate-mcp` and `desk-gateway`, and re-run the probes through the services (`/brief`,
`events_emit`, `/health`). Only after this passes does step 5 start.

## 5. Retire public exposure — G-6

Removing the TimescaleDB TCP proxy and the Greptime public domain is an access change.
Record the approval in the INFRA receipt **before** acting, with this rollback plan:

- Rollback: re-create the TCP proxy on the TimescaleDB service (Settings → Networking → TCP
  Proxy, or `create-tcp-proxy`) and re-generate the Greptime domain (`generate-domain`). Minutes;
  no data implication. A re-created proxy gets a **new** public port, so any consumer that still
  used the old address needs the new one — the point of step 4 is that none do.
- Then: delete the TimescaleDB TCP proxy (`delete-tcp-proxy`); remove the Greptime public domain
  (`delete-domain`). Keep `hindsight-ui` on its Railway domain behind its access key only if Ove
  wants browser access without the tailnet; otherwise remove it too and use the Mac mini.
- Evidence: `tailscale status`, the port probes from step 3, the CLI output or dashboard
  screenshot of the removals, and the approval id, all in the receipt.

## 6. `railway-app` (100.77.7.42)

Identify which project this existing tailnet node belongs to. If it is the deprecated subnet
router or an exit node, retire it after both forwarders are verified (a second G-6). If it is
already a forwarder for one of these projects, adopt it and skip the duplicate.

## Bot computers

Grok Bot computers are **not** on the tailnet and get nothing from this. They reach the desk over
`https://desk.swcstudio.space` only. If the Cursor team uses an egress allowlist, add that host.
