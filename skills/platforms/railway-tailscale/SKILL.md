---
name: railway-tailscale
description: Reach the Railway data planes over Tailscale Forwarders, cut the VPS over, retire public endpoints under G-6, and roll back.
bots: [5]
gates: [G-5, G-6]
---

# Railway over Tailscale

## When this applies (L1)

INFRA only. The five Railway services (Ultrathink: GreptimeDB, TimescaleDB, DragonflyDB; Agent
Substrate: Hindsight, RAGFlow) are reached from the VPS over the tailnet by MagicDNS name, through
a **Tailscale Forwarder** deployed inside each Railway project. Railway private networking is per
project and per environment, so one forwarder per project is the minimum and there is no
cross-project shortcut. After cutover the public TCP proxy and public database domains are
retired (G-6). Bot computers never join the tailnet; they reach the gateway over normal egress.

```
Standing up or changing the Railway ↔ VPS path?
│
├─ New project or environment ──▶ One forwarder per project/environment. §1–§2
├─ Adding a service to reach ──▶ New CONNECTION_MAPPING_n on that project's forwarder. §2
├─ ACL change ──▶ Tags only: tag:railway-forwarder, tag:vps, tag:admin. §3
├─ Cutting the VPS over ──▶ Verify (desk_tailscale_status, desk_db_health) → env → restart →
│                           verify again → retire public exposure under G-6 with approval. §4–§5
├─ Something broke after cutover ──▶ Roll back: revert env by file, restart; re-create the proxy
│                                     or domain if it was already removed. §6
├─ Slice, index archive, /livez, or metrics history ──▶ §8. No gateway tool does these.
└─ Writing the receipt ──▶ §7. TS_AUTHKEY and connection strings never appear in it.
```

The five data planes named in this skill (GreptimeDB, TimescaleDB, DragonflyDB, Hindsight,
RAGFlow) are the services agent-substrate `91487e7` (#59, "discovery of five Railway services")
builds R1–R7 against. The history digest's commit subject names the discovery; it does not list
Railway service ids, so this skill does not invent ids. Hostnames and ports in §2 stay this
desk's forwarder record.

`9231f43` (#60) records that release `91487e7` is live (tag `release-20261013-91487e7`). That is
the substrate release. It is not a record that the public TCP proxy and public database domains
in §5 have been retired. Those remain a G-6 step with an approval id.

`1e5e719` (#62) hardens the VPS runtime (slice priority and swap isolation, a store-free
`/livez`, an opt-in watchdog), keeps TTL'd `metric_samples` history with a bounded
`/slo/history`, and adds index disaster recovery (logical export, offline verify,
restore-to-scratch). Every policy in that commit ships off or report-only, and the commit says
nothing deletes production data. This skill does not enable those policies. §8 lists the gateway
tools that exist and the follow-ups that do not.

---

## Method (L2)

### §1 Why one forwarder per project

`*.railway.internal` resolves only inside the project and environment that owns the service, and
not from the VPS at all (the substrate env comment records this). A forwarder is a Railway service
that joins the tailnet and proxies listed ports to `<service>.railway.internal`. Two projects,
two forwarders; a second environment (staging) is a third.

### §2 Forwarder configuration

Deploy Railway's Tailscale Forwarder template (it replaced the deprecated subnet-router template)
into each project. Variables:

| Variable | Value | Consequence if wrong |
|---|---|---|
| `TS_AUTHKEY` | A **reusable, tagged** key from the Tailscale admin console, tag `tag:railway-forwarder`, ephemeral **off**, key expiry disabled on the resulting machine | A one-off key breaks the next redeploy; an ephemeral node vanishes on restart and every mapping with it; an untagged node gets no ACL grant |
| `CONNECTION_MAPPING_n` | `<src_port>:<service>.railway.internal:<port>`, one per service, `n` = 1, 2, … | A typo in the service name is a mapping to nothing; the port probe in §4 is how you find it |
| Volume | Mounted for Tailscale state, so the machine identity survives redeploys | Without it each redeploy is a new machine with a new name and the VPS env points at a ghost |

Machine name: `<project>-<environment>-tailscale-forwarder`. The VPS env uses these names, never
the tailnet IP, which changes when the node is re-created. Expected mappings are this desk's
forwarder record. `91487e7` names the five data planes and does not restate these hostnames:

| Forwarder | Mappings |
|---|---|
| `ultrathink-production-tailscale-forwarder` | `4000:greptimedb.railway.internal:4000` (HTTP SQL), `4001:…:4001` (gRPC), `4003:…:4003` (PG wire), `5432:timescaledb.railway.internal:5432`, `6379:dragonfly.railway.internal:6379` |
| `agent-substrate-production-tailscale-forwarder` | `8888:hindsight-api.railway.internal:8888`, `9380:ragflow.railway.internal:9380`, optionally `80:ragflow.railway.internal:80` |

Traffic inside the tailnet is WireGuard-encrypted, so plaintext service ports on the forwarder hop
are acceptable. Hindsight and RAGFlow still require their bearer keys: the tailnet replaces the
public exposure, not the application auth.

### §3 ACL

| Tag | Applied to |
|---|---|
| `tag:railway-forwarder` | Both forwarders (via the auth key) |
| `tag:vps` | The VPS |
| `tag:admin` | Ove's Mac mini and XPS |

Grants: `tag:vps → tag:railway-forwarder` on the mapped ports; `tag:admin → tag:railway-forwarder`
on the same; nothing else. Deny by default. A grant to `*` or to an untagged node is an ACL
change QUALITY should see before it is applied, because it widens who can reach a database.

Check the `railway-app` node (100.77.7.42) in n1: a deprecated subnet router or exit node is
retired under G-6 after the forwarders are verified; an existing forwarder is adopted, not duplicated.

### §4 Verify before touching the VPS

1. `desk_tailscale_status` — both forwarders online, this node tagged `tag:vps`, mapped ports reachable.
2. From the VPS shell (`skills/platforms/remote-dev-machine`; SSH is INFRA-owned ops): `psql` to
   `ultrathink-production-tailscale-forwarder:5432`, `curl` to `:4000` and to
   `agent-substrate-production-tailscale-forwarder:8888/health` and `:9380`. Record each exit code.
3. `desk_db_health` — greptime, timescale, dragonfly, hindsight and ragflow ok over the tailnet
   names, and the substrate row present, before any env changes. The substrate row is
   `GET /healthz`. `1e5e719` adds a store-free `/livez`; this probe is not that route.

If any probe fails here, stop. The cutover has nothing to cut over to yet.

### §5 Cutover order

1. Edit `/etc/substrate/substrate.env` and `/etc/desk-gateway/gateway.env`: `GREPTIME_URL`,
   `SUBSTRATE_PG_URL`, `DRAGONFLY_URL`, `HINDSIGHT_URL`, `RAGFLOW_URL` to the forwarder names.
   Keep a dated copy of each file beside it; that copy is the rollback.
2. Restart `substrate-mcp` and `desk-gateway`. `desk_vps_units` shows them active. The gateway
   default list is those two plus `substrate-host`, `substrate-dispatcher`, `vps-agent-bus` and
   `grok-claude-cloud-connector`. It is not a glob of `substrate-*`. `91487e7` (R7) places
   substrate units in `substrate.slice`. `9231f43` teaches `parity:check` to accept that slice
   or `system.slice`; before that commit only `system.slice` passed, so the R7 slice failed the
   check. There is no gateway tool for `parity:check`. Units added in `1e5e719`
   (`substrate-index-archive`, `substrate-docs-canary`, `substrate-alert@`) appear in
   `desk_vps_units` only when named in `units`.
3. Verify again: `desk_db_health` ok for the five planes and the substrate `/healthz` row;
   `desk_event_emit` lands; `desk_brief` returns. Record the calls. A green `/healthz` is not a
   reading of `/livez`, and a landed event is not a `metric_samples` row (`1e5e719` S6).
4. Only now retire public exposure (G-6): delete the TimescaleDB TCP proxy and the Greptime
   public domain, in the Railway dashboard or CLI. There is deliberately no gateway tool for
   this; it is a human-approved destructive change with an `approval_id` obtained through LEAD
   and recorded in the receipt. Keep `hindsight-ui` on a Railway domain behind its access key
   only if Ove wants browser access without the tailnet.
5. Verify a third time. A service still reachable on its public address is a step 4 that did not
   finish.

Steps 1–3 before step 4, always: retiring the proxy first leaves the substrate pointing at a host
that no longer answers, and the outage lasts until someone notices.

### §6 Rollback

| Symptom | Action | Time | Data |
|---|---|---|---|
| `desk_db_health` red after restart | Restore the dated env copies; restart the units | Minutes | None |
| Public proxy or domain already removed and needed back | Re-create the TCP proxy / domain in Railway; the new proxy has a **new** host and port, so update the env accordingly | Minutes | None; the database did not move |
| Forwarder unhealthy | Redeploy it (the volume keeps its identity); if it re-registers as a new machine, the volume was missing | Minutes | None |

None of these has a data implication; the services never moved. Say so in the receipt (G-5 asks).

### §7 The receipt

`.receipts/bot-05-infrastructure/<task>.json` with: `desk_tailscale_status` output tail; each port
probe with exit code; `desk_db_health` before and after; the env diff **by variable name only**
(never the values); `desk_vps_units` after restart; the Railway proxy/domain removal (CLI output
or screenshot reference); `approvals` with the G-6 approval id; `rollback_plan` from §6;
`unverified` for anything not exercised (staging environment, `railway-app` disposition, ACL
from the admin machines if not probed). `TS_AUTHKEY`, database passwords and bearer keys are
never in the receipt, a template, a message or a tool argument (G-3, PD-4). Do not record a
`parity:check` pass, a `/livez` probe, an index-archive verify, or a `/slo/history` read unless
that command actually ran. None of those have a gateway tool (§8).

---

## Worked example

**Good — ordering that survives a bad mapping.**

```
desk_tailscale_status → agent-substrate forwarder online; port 9380 unreachable
curl agent-substrate-production-tailscale-forwarder:9380 → exit 7          ← mapping typo found
fix CONNECTION_MAPPING_2 in Railway → redeploy forwarder → curl → exit 0
desk_db_health → five planes and substrate /healthz ok (public addresses still in env)
edit env (dated copies kept) → restart → desk_vps_units active → desk_db_health ok again
approval via LEAD → apr-… → delete TCP proxy + Greptime domain → desk_db_health ok again
receipt: probes, env names, approval id, rollback plan, unverified: ["staging not built"]
```

**Bad — same change, proxy first.**

```
delete TimescaleDB TCP proxy ("we're moving anyway") → substrate-mcp loses Timescale →
intake queue and claims unavailable for 40 minutes while the forwarder mapping is debugged.
```

Nothing was lost, and the desk was down for the whole debugging session because the old path was
removed before the new one was proven. The order in §5 exists for this case.

---

## Failure modes

| Mode | Symptom | Fix |
|---|---|---|
| One forwarder for two projects | Second project's services never resolve | One forwarder per project/environment |
| Ephemeral or one-off auth key | Forwarder gone or unable to rejoin after redeploy | Reusable, tagged key; ephemeral off; expiry disabled |
| No volume | New machine name on every redeploy | Mount the state volume |
| IP in env instead of name | Breaks when the node is re-created | Use the MagicDNS machine name |
| Proxy retired before cutover verified | Outage while debugging | §5 order; verify three times |
| ACL grant to `*` | Any tailnet node can reach a database | Tag-to-tag grants only; QUALITY sees widenings |
| Secret in receipt or message | Key or password in a JSON tail | Names only; rotate what leaked |
| Bot computer on the tailnet | Bot depends on a desktop being awake; holds a route to databases | Bots use the gateway over normal egress |
| `railway-app` left as an unknown node | Untagged node with unknown reach | Identify in n1; adopt or retire under G-6 |
| `parity:check` fails the R7 slice | Checker accepts only `system.slice` | Fixed in `9231f43`: the unit cgroup may be `substrate.slice` or `system.slice`. No desk tool runs the checker |
| Green `desk_db_health` read as `/livez` | Store-free liveness was not probed | The gateway calls `/healthz`. `/livez` is `1e5e719` and has no roster tool |
| Index archive or `/slo/history` driven from this skill | A restore or a history read with no gateway tool | §8. Policies in `1e5e719` ship off or report-only |

---

## §8 What `91487e7`, `9231f43` and `1e5e719` do not add to the gateway

Facts below are from the agent-substrate history digest (`git log --stat` since `feb597f`), not
from a clone of that repo. The gateway implementations checked are
`services/desk-gateway/src/desk_gateway/tools/infra.py`, `tools/core.py` and `upstreams.py`.

| Commit | What landed in agent-substrate | Desk tool that already covers the adjacent fact | Not a roster tool |
|---|---|---|---|
| `91487e7` #59 | Discovery of the five Railway data-plane services; R7 cgroup ceilings in `substrate.slice`; R1 brief fast path; R3 Hindsight retain outbox; R6 RAGFlow dataset pins | `desk_railway_status`, `desk_db_health`, `desk_tailscale_status`, `desk_brief`, `desk_memory_retain`, `desk_docs_search` | No etag / If-None-Match / profile on `desk_brief`. No client of the retain outbox |
| `9231f43` #60 | `openGraphs` in two round trips; `parity:check` accepts `substrate.slice` or `system.slice` | `desk_brief` (the budget failure mode). `desk_vps_units` still reports ActiveState only | No `desk_parity_check` |
| `1e5e719` #62 | Slice priority and swap isolation; store-free `/livez` and an opt-in watchdog; TTL'd `metric_samples` and bounded `/slo/history`; index logical export, offline verify, restore-to-scratch; units `substrate-index-archive`, `substrate-docs-canary`, `substrate-alert@` | `desk_db_health` still calls `/healthz`. `desk_event_emit` still writes the event log. `desk_vps_units` can show the new units when `units` names them | No `/livez` probe, no metrics-history read, no index-archive tool. A restore tool would be g6 and is not added |

Follow-ups, each of which needs gateway code before a roster entry:

1. `desk_brief` inputs for the `91487e7` fast path (etag, If-None-Match, profile). The production loop treats a missing etag as the no-marker condition. Adding the field is a later contract change, not this one.
2. A `/livez` reading distinct from `desk_db_health`'s `/healthz` (`1e5e719` S3), including the opt-in watchdog. `infra.db_health` does not call `/livez`.
3. A read-only index-archive verify (`1e5e719` S2). Restore-to-scratch is not a read tool; pointed at a live database it would be g6. Neither backend exists.
4. A read of `metric_samples` / `/slo/history` (`1e5e719` S6). `desk_event_emit` and `desk_railway_logs` are different stores.
5. `parity:check` as a tool. It is a substrate script. `desk_vps_units` does not report which slice a unit is in.
6. Putting `substrate-index-archive`, `substrate-docs-canary` and `substrate-alert@` on the default `desk_vps_units` list. The default is `DEFAULT_UNITS` in `infra.py`. Changing it is gateway code. Callers can pass `units` today.

`coordination_graph_heartbeat` and `coordination_drift_scan` are unchanged as inputs.
`91487e7` R4 keeps a swept graph while a live lease is held, which is why a rejected heartbeat
still means stop. No DriftKind for slice, archive or metrics history is declared by these three
commits, so the drift tool does not grow one.

---

## Gate mapping

| Rule | Gate or directive | Why |
|---|---|---|
| Rollback plan with time and data implications in the receipt | G-5 | Env-by-file revert and proxy re-creation are the plan; "no data moved" is the data line |
| Proxy and domain removal need a recorded approval | G-6, PD-5 | Removing public access is destructive to anything still using it |
| No `TS_AUTHKEY`, passwords or bearer keys anywhere but the secret stores | G-3, PD-4 | Receipts, templates and messages are copied |
| Every probe recorded with its exit code; the unprobed goes in `unverified` | G-2, PD-1, PD-6 | "Reachable over the tailnet" is a claim a re-run must be able to check |
| `infra/railway/**`, `infra/tailscale/**` are INFRA's; ACL widenings go past QUALITY | G-1, PD-2 | Ownership is already declared for these paths |
| Do not add a roster tool the gateway does not implement | G-4, PD-2 | Slice check, `/livez`, index archive and metrics history are follow-ups until `infra.py` grows a backend |
