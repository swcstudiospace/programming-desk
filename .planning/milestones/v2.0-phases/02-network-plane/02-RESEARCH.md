# Phase 2: Network plane — Research

**Researched:** 2026-10-08  
**Domain:** Railway over Tailscale, private per-project forwarders, exact-port least-privilege ACL, substrate cutover, and G-6 exposure retirement  
**Confidence:** HIGH based on authoritative repository artifacts (`docs/upgrade-plan-desk-v2.md` §5, `infra/railway/forwarders.yaml`, `infra/tailscale/policy.hujson`), live host observations (`tailscale status`, `railway service list`), and verified Phase 1 inventory (`n1-platform.json`).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01 (Forwarder Mapping & Listener Isolation):** Map strictly the source-authorized ports:
  - Ultrathink / production: 4000 (Greptime HTTP SQL), 4001 (Greptime gRPC), 4003 (Greptime PG wire), 5432 (TimescaleDB), 6379 (DragonflyDB). Mappings do NOT expand to unauthorized listener 4002 observed in Phase 1.
  - Agent Substrate / production: 8888 (Hindsight API REST & `/mcp/<bank>/`), 9380 (RAGFlow API), 80 (RAGFlow Web UI, explicitly optional). Mappings do NOT expand to unauthorized listener 9382 observed in Phase 1.
  - Persistence: Machine identity persists on a persistent volume mounted at `/var/lib/tailscale`.
  - Machine names: `ultrathink-production-tailscale-forwarder` and `agent-substrate-production-tailscale-forwarder`.
  - Enrollment: `tag:railway-forwarder`, key expiry disabled, auth key reusable non-ephemeral tagged. No secret auth key value enters any repository artifact or receipt.
  - `railway-app` (100.77.7.42): Retained as the observed subnet-route advertiser; not adopted as a forwarder (unproven suitability) and not retired without G-6 approval after forwarders are verified.

- **D-02 (Exact-Port Least Privilege Matrix):**
  - Permitted devices: `tag:vps` (187.77.130.10, `100.90.229.45`), `tag:admin` (Ove's Mac mini `100.80.62.2`, XPS `100.104.90.39`).
  - Grants: EXACT mapped ports only (`tcp:4000`, `tcp:4001`, `tcp:4003`, `tcp:5432`, `tcp:6379`, `tcp:8888`, `tcp:9380`, `tcp:80`). No broad `tcp:4000-4003` range (which would permit unauthorized port 4002).
  - Deny-by-default: All other principals and all other ports denied. Forwarders cannot initiate connections to VPS or admin devices (`tag:railway-forwarder` has no outbound grants).
  - Grok Bots: Do NOT join tailnet, hold NO database credentials. Normal HTTPS egress to `desk.swcstudio.space`.
  - Team allowlist includes `desk.swcstudio.space`. Mac mini egress routing documented as INFRA-only emergency path dependent on Mac mini remaining awake.

- **D-03 (Multi-Device Path Verification):**
  - Protocol-level probes for VPS (`curl` for HTTP/REST, `pg_isready` for Postgres wire, `redis-cli PING` for Dragonfly).
  - Multi-device verification: VPS, Mac mini, and XPS are distinct device paths. Mac mini probes evidenced separately from VPS. Offline status of XPS (last seen 5d ago) recorded honestly as unexercised/unverified if unreachable during probes; design approval alone is not probe evidence.

- **D-04 (Substrate Environment Cutover & Runtime Assurance):**
  - Cutover `/etc/substrate/substrate.env` to MagicDNS forwarder hosts (`ultrathink-production-tailscale-forwarder`, `agent-substrate-production-tailscale-forwarder`).
  - Restart `substrate-mcp.service` (resolving the port 7410 collision with orphaned PID 3149064).
  - Verify `/brief` (`POST /brief`) and `events_emit` (`POST /events`) against the cutover configuration. WireGuard encryption protects plaintext service hops; Hindsight and RAGFlow bearer auth retained.

- **D-05 (G-6 Exposure Retirement & Rollback):**
  - Removal of TimescaleDB TCP proxy (`monorail.proxy.rlwy.net:49679`) and Greptime public domain (`greptimedb-production.up.railway.app`) is an access change requiring genuine G-6 approval (`approved_by`, `approval_id`) and concrete re-create rollback plans.
  - Retirement occurs ONLY after forwarder connectivity and cutover paths are verified.
  - Rollback procedure: re-create TCP proxy on TimescaleDB, re-generate domain on GreptimeDB, restore `/etc/substrate/substrate.env` from backup.
  - `hindsight-ui` exposure kept on Railway domain only if Ove specifically requests browser access without tailnet, else Mac mini tailnet path.

- **D-06 (Evidence & Receipt Discipline):**
  - Publish receipt `.receipts/bot-00-programming-lead/n2-network.json` containing `tailscale status`, port probes, removal evidence, rollback, and exhaustive `unverified` list covering every unexercised path.

</user_constraints>

## Summary

Phase 2 replaces vulnerable public database TCP proxies and public database domains with private, encrypted Tailscale Forwarders connected directly to Railway's internal network (`fd12::/16`, `*.railway.internal`). Because Railway isolates private networks by project and environment, cross-project communication requires one forwarder per project:
1. **Ultrathink / production**: forwards GreptimeDB (4000 HTTP, 4001 gRPC, 4003 Postgres wire), TimescaleDB (5432), and DragonflyDB (6379).
2. **Agent Substrate / production**: forwards Hindsight API (8888) and RAGFlow API (9380), with optional RAGFlow Web UI (80).

Security is enforced via Tailscale ACL tags (`tag:railway-forwarder`, `tag:vps`, `tag:admin`) with strict deny-by-default rules. In accordance with constraint RW-02, permitted grants are limited strictly to exact mapped ports, explicitly excluding the unauthorized listeners identified in Phase 1 (Greptime 4002 and RAGFlow 9382).

VPS substrate environment cutover (`/etc/substrate/substrate.env`) switches database and service connections from public hosts to MagicDNS forwarder hostnames. The cutover is verified at runtime by restarting `substrate-mcp` and validating both `/brief` composition and `events_emit` audit logging. Only after forwarder connectivity and runtime cutover are fully verified may public TCP proxies and domains be retired under Gate G-6 with recorded approval and verified re-creation rollback plans.

## Architectural Responsibility Map

| Role / Surface | Owner | Boundary & Responsibility |
|---|---|---|
| Phase Orchestration & Receipts | `bot-00-programming-lead` | Orchestrates Phase 2 plans, tracks dependencies, records receipt `.receipts/bot-00-programming-lead/n2-network.json`. |
| Forwarder Deployment & IaC | `bot-05-infrastructure` | Owns `infra/railway/**` and `infra/tailscale/**`. Provisions and manages forwarders and ACLs. |
| Substrate Runtime & MCPServer | `bot-01-systems-backend` | Owns `agent-substrate` services (`substrate-mcp`). Validates post-cutover `/brief` and `events_emit`. |
| Quality Gates & G-6 Governance | `bot-06-quality-security` | Enforces G-1, G-2, G-6 access approval verification, and receipt schema compliance. |

## 1. Forwarder Deployment Architecture

### 1.1 Project Isolation and Mapping Matrix
Railway private networking is scoped per project. Services in `Ultrathink` cannot communicate with services in `Agent Substrate` over Railway internal DNS without an intermediary.

```
+-----------------------------------------------------------------------------------------+
|                                    TAILSCALE TAILNET                                    |
|                               (hedgehog-mooneye.ts.net)                                 |
|                                                                                         |
|  +--------------------+        +--------------------+        +--------------------+     |
|  |        VPS         |        |   Ove's Mac mini   |        |     Ove's XPS      |     |
|  |   100.90.229.45    |        |    100.80.62.2     |        |   100.104.90.39    |     |
|  |     (tag:vps)      |        |    (tag:admin)     |        |    (tag:admin)     |     |
|  +---------+----------+        +---------+----------+        +---------+----------+     |
+------------|-----------------------------|-----------------------------|----------------+
             |                             |                             |
             +-----------------------------+-----------------------------+
                                           |
                        WireGuard Encrypted Tailnet Mesh
                                           |
             +-----------------------------+-----------------------------+
             |                                                           |
+------------v-------------------------------+   +-----------------------v-----------------------+
| Railway Project: Ultrathink / production   |   | Railway Project: Agent Substrate / production |
| Machine:                                   |   | Machine:                                      |
| ultrathink-production-tailscale-forwarder  |   | agent-substrate-production-tailscale-forwarder|
| Tag: tag:railway-forwarder                 |   | Tag: tag:railway-forwarder                    |
| State: /var/lib/tailscale (Volume)         |   | State: /var/lib/tailscale (Volume)            |
|                                            |   |                                               |
| Mappings:                                  |   | Mappings:                                     |
|  - 4000 -> greptimedb.railway.internal:4000|   |  - 8888 -> hindsight-api.railway.internal:8888|
|  - 4001 -> greptimedb.railway.internal:4001|   |  - 9380 -> ragflow.railway.internal:9380      |
|  - 4003 -> greptimedb.railway.internal:4003|   |  - 80   -> ragflow.railway.internal:80 (opt)  |
|  - 5432 -> timescaledb.railway.internal:5432|  +-----------------------------------------------+
|  - 6379 -> dragonfly.railway.internal:6379 |
+--------------------------------------------+
```

### 1.2 Forwarder Configuration Specifications

#### Ultrathink Forwarder
- **Machine Name:** `ultrathink-production-tailscale-forwarder`
- **Template Code:** `tailscale-forwarder` (Railway Marketplace template `5ffa6b42-0331-428d-b102-0f1935022763`)
- **Persistent Volume:** Mounted at `/var/lib/tailscale` (prevents node duplicate generation across redeploys)
- **Tailscale Auth Key:** Tagged `tag:railway-forwarder`, Reusable, Non-ephemeral, Pre-approved. Key expiry explicitly disabled in Tailscale Admin Console.
- **Environment Variables:**
  - `TS_AUTHKEY`: `[REDACTED]` (configured in Railway dashboard, never in git)
  - `CONNECTION_MAPPING_1`: `4000:greptimedb.railway.internal:4000`
  - `CONNECTION_MAPPING_2`: `4001:greptimedb.railway.internal:4001`
  - `CONNECTION_MAPPING_3`: `4003:greptimedb.railway.internal:4003`
  - `CONNECTION_MAPPING_4`: `5432:timescaledb.railway.internal:5432`
  - `CONNECTION_MAPPING_5`: `6379:dragonfly.railway.internal:6379`
- **Listener Isolation:** Port 4002 (unauthorized Greptime listener) is explicitly omitted from mappings.

#### Agent Substrate Forwarder
- **Machine Name:** `agent-substrate-production-tailscale-forwarder`
- **Template Code:** `tailscale-forwarder`
- **Persistent Volume:** Mounted at `/var/lib/tailscale`
- **Tailscale Auth Key:** Tagged `tag:railway-forwarder`, Reusable, Non-ephemeral, Pre-approved. Key expiry explicitly disabled in Tailscale Admin Console.
- **Environment Variables:**
  - `TS_AUTHKEY`: `[REDACTED]`
  - `CONNECTION_MAPPING_1`: `8888:hindsight-api.railway.internal:8888`
  - `CONNECTION_MAPPING_2`: `9380:ragflow.railway.internal:9380`
  - `CONNECTION_MAPPING_3`: `80:ragflow.railway.internal:80` (optional web UI)
- **Listener Isolation:** Port 9382 (unauthorized RAGFlow listener) is explicitly omitted from mappings.

### 1.3 `railway-app` Status and Role
`railway-app` (`100.77.7.42`) was identified in Phase 1 as running service `tailscale-vpn` in Ultrathink. It acts as an observed subnet-route advertiser (`10.128.0.0/9`, `fd12:4f8:a4d6:1::/64`, `fd12::10/128`). Per `REQ-NETWORK-015`, it is unproven as a port forwarder and is NOT adopted in place of dedicated forwarders. It remains undisturbed during Phase 2; retirement is deferred to Phase 7 under Gate G-6.

## 2. Tailscale ACL & Exact-Port Policy Architecture

### 2.1 Least Privilege Policy
The ACL policy governs communication across the tailnet:
1. `tag:railway-forwarder`: Owned by `autogroup:admin`. Represents the two Railway forwarders.
2. `tag:vps`: Owned by `autogroup:admin`. Represents the production VPS (`100.90.229.45`).
3. `tag:admin`: Owned by `autogroup:admin`. Represents Ove's Mac mini (`100.80.62.2`) and XPS (`100.104.90.39`).

### 2.2 Exact-Port Rule Correction (Constraint RW-02)
`infra/tailscale/policy.hujson` on `origin/main` contained `"tcp:4000-4003"`. This port range violates constraint RW-02 and REQ-NETWORK-005/021 by opening port 4002. The corrected policy enforces exact-port grants:
```json
"grants": [
  {
    "src": ["tag:vps", "tag:admin"],
    "dst": ["tag:railway-forwarder"],
    "ip": [
      "tcp:4000",
      "tcp:4001",
      "tcp:4003",
      "tcp:5432",
      "tcp:6379",
      "tcp:8888",
      "tcp:9380",
      "tcp:80"
    ]
  }
]
```

### 2.3 Deny-by-Default Invariants
- `tag:railway-forwarder` has ZERO outbound grants. A compromised forwarder cannot initiate connections back to the VPS or admin devices.
- Grok Bots are NOT enrolled in the tailnet and hold no tailscale credentials.
- All non-mapped ports on forwarders (e.g. SSH 22, HTTPS 443, metrics 4002/9382) are denied.

## 3. Multi-Device Path Verification Strategy

### 3.1 Device Reachability Matrix
| Device | Tailscale IP | Hostname | Expected Status | Verification Method |
|---|---|---|---|---|
| VPS | `100.90.229.45` | `vps.hedgehog-mooneye.ts.net.` | Online | Direct execution of CLI probes (`curl`, `pg_isready`, `redis-cli`) |
| Mac mini | `100.80.62.2` | `oves-mac-mini.hedgehog-mooneye.ts.net.` | Online | Remote verification or operator probe script |
| XPS | `100.104.90.39` | `ove-xps-15.hedgehog-mooneye.ts.net.` | Offline (5d ago) | Documented as offline/unverified in receipt per D-03 |

### 3.2 Protocol-Level Probes
1. **GreptimeDB HTTP SQL (4000):**
   `curl -sf http://ultrathink-production-tailscale-forwarder:4000/health`
2. **GreptimeDB Postgres Wire (4003):**
   `pg_isready -h ultrathink-production-tailscale-forwarder -p 4003`
3. **TimescaleDB Postgres (5432):**
   `pg_isready -h ultrathink-production-tailscale-forwarder -p 5432`
4. **DragonflyDB Redis (6379):**
   `redis-cli -h ultrathink-production-tailscale-forwarder -p 6379 PING` (Expect `PONG` or `NOAUTH`)
5. **Hindsight API (8888):**
   `curl -sf http://agent-substrate-production-tailscale-forwarder:8888/health`
6. **RAGFlow API (9380):**
   `curl -s -o /dev/null -w "%{http_code}\n" http://agent-substrate-production-tailscale-forwarder:9380/`

## 4. Substrate Environment Cutover & Runtime Service Verification

### 4.1 Substrate Environment (`/etc/substrate/substrate.env`)
The cutover replaces public URLs with internal MagicDNS forwarder URLs:
- `GREPTIME_URL=http://ultrathink-production-tailscale-forwarder:4000`
- `SUBSTRATE_PG_URL=postgresql://[AUTH]@ultrathink-production-tailscale-forwarder:5432/railway`
- `DRAGONFLY_URL=redis://[AUTH]@ultrathink-production-tailscale-forwarder:6379/0`
- `HINDSIGHT_URL=http://agent-substrate-production-tailscale-forwarder:8888`
- `RAGFLOW_URL=http://agent-substrate-production-tailscale-forwarder:9380`

### 4.2 Runtime Collision Remediation
During research, `substrate-mcp.service` was observed failing to bind port 7410 due to orphaned process PID 3149064. Prior to cutover restart:
1. Identify and cleanly terminate orphaned process PID 3149064.
2. Restart `substrate-mcp.service` via `systemctl restart substrate-mcp`.
3. Verify listening state on `127.0.0.1:7410`.

### 4.3 Runtime Verification Calls
1. **Brief Verification:** `curl -s -X POST http://127.0.0.1:7410/brief` (verifies index store connection and synthesis).
2. **Event Emit Verification:** `curl -s -X POST http://127.0.0.1:7410/events` with valid event JSON (proves Greptime post-cutover audit path).

## 5. Public Exposure Retirement & G-6 Rollback Plan

### 5.1 G-6 Governed Actions
Public database endpoints must be decommissioned to seal the network perimeter:
1. **TimescaleDB TCP Proxy:** `monorail.proxy.rlwy.net:49679` (delete proxy on service `1bd7a6fd-b7b2-4fe4-8b4f-0d76ead81d79`).
2. **GreptimeDB Public Domain:** `greptimedb-production.up.railway.app` (remove domain on service `b53b4c7d-df3c-4cd8-a15d-e5fb1a79e254`).
3. **Hindsight UI:** Kept on Railway domain only if Ove requests browser access without tailnet; otherwise managed via Mac mini tailnet path.

### 5.2 Rollback Procedures (Pre-computed and Instant)
- **TimescaleDB TCP Proxy Rollback:** Re-create TCP proxy via Railway CLI (`railway tcp-proxy`) or dashboard. Note: re-created proxy receives a new public port; consumers must be updated if public access is restored.
- **GreptimeDB Public Domain Rollback:** Re-generate public domain via Railway CLI (`railway domain`) or dashboard.
- **Substrate Environment Rollback:** Restore `/etc/substrate/substrate.env` from `/etc/substrate/substrate.env.bak.[timestamp]` and restart `substrate-mcp`.

## 6. Threat Model (ASVS 5.0 Level 1)

| Threat ID | ASVS 5.0 | Category | Component | Severity | Disposition | Mitigation Plan |
|---|---|---|---|---|---|---|
| T-02-01 | V1 Architecture | Elevation of Privilege | Tailscale ACL | High | Mitigate | Exact-port grants in ACL; broad ranges (4000-4003) rejected; ports 4002 and 9382 explicitly excluded. |
| T-02-02 | V6 Authentication | Information Disclosure | TS_AUTHKEY Exposure | High | Mitigate | Store TS_AUTHKEY strictly in Railway environment variables; redact all auth keys and passwords from receipts and git. |
| T-02-03 | V8 Authorization | Elevation of Privilege | Forwarder Lateral Movement | High | Mitigate | `tag:railway-forwarder` has zero outbound grants; cannot pivot into VPS or admin machines. |
| T-02-04 | V9 Communications | Information Disclosure | Plaintext Service Ports | Medium | Mitigate | Plaintext forwarder hops travel strictly inside WireGuard-encrypted tailnet tunnels; bearer tokens retained for HTTP services. |
| T-02-05 | V14 Business Logic | Service Disruption | Premature Public Exposure Removal | High | Mitigate | Retirement occurs strictly AFTER cutover probes and runtime verification pass; rollback plans verified beforehand. |

## 7. Requirement Traceability Matrix

| Requirement | Description | Assigned Plan |
|---|---|---|
| REQ-NETWORK-001 | Ultrathink forwarder mappings (4000, 4001, 4003, 5432, 6379) | 02-01 |
| REQ-NETWORK-002 | Agent Substrate forwarder mappings (8888, 9380; optional 80) | 02-01 |
| REQ-NETWORK-003 | Machine identity persistence on volume, project/environment scoped | 02-01 |
| REQ-NETWORK-004 | `tag:railway-forwarder`, disabled expiry, reusable tagged auth key | 02-01 |
| REQ-NETWORK-005 | ACL exact-port grants for `tag:vps` and `tag:admin`; deny-default | 02-02 |
| REQ-NETWORK-006 | VPS tailnet port probe evidence (protocol-level) | 02-03 |
| REQ-NETWORK-007 | Mac mini administrative path port probe evidence (evidenced separately) | 02-03 |
| REQ-NETWORK-008 | Substrate environment cutover to MagicDNS forwarder hosts | 02-04 |
| REQ-NETWORK-009 | `substrate-mcp` restart and `/brief` verification | 02-04 |
| REQ-NETWORK-010 | `events_emit` invocation recorded proving post-cutover event path | 02-04 |
| REQ-NETWORK-011 | G-6 approval and re-create rollback for TimescaleDB TCP proxy retirement | 02-05 |
| REQ-NETWORK-012 | G-6 approval and re-create rollback for Greptime public domain retirement | 02-05 |
| REQ-NETWORK-013 | Public database retirement occurs ONLY after replacement path verified | 02-05 |
| REQ-NETWORK-014 | `hindsight-ui` browser access exposure governance | 02-05 |
| REQ-NETWORK-015 | `railway-app` adoption evaluation; unidentified node not assumed suitable | 02-01 |
| REQ-NETWORK-016 | Grok Bot HTTPS egress only, no tailnet membership or DB credentials | 02-02 |
| REQ-NETWORK-017 | Team allowlist includes `desk.swcstudio.space` | 02-02 |
| REQ-NETWORK-018 | Mac-mini-routed egress emergency path documented as INFRA-only | 02-02 |
| REQ-NETWORK-019 | Plaintext mapped ports WireGuard-encrypted; bearer keys retained | 02-03 |
| REQ-NETWORK-020 | n2 receipt published with status, probes, removal, rollback, unverified | 02-06 |
| REQ-NETWORK-021 | VPS, Mac mini, and XPS permitted device paths evidenced; other ports denied | 02-03 |
| REQ-NETWORK-022 | Mac mini and XPS approved `tag:admin` receive exact-port grants alongside VPS | 02-02 |
