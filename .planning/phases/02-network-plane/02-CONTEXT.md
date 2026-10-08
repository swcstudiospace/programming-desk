# Phase 2: Network plane — Context

**Gathered:** 2026-10-08  
**Status:** Ready for research and planning; not executed or verified  
**Mode:** Autonomous smart discussion. Governed by `docs/upgrade-plan-desk-v2.md` §5, `ownership.yaml`, `docs/desk-operating-model.md`, and REQ-NETWORK-001 through REQ-NETWORK-022.

<domain>
## Phase Boundary

Phase 2 delivers Workstream A (Railway over Tailscale) and source step n2 (`docs/upgrade-plan-desk-v2.md` §5 and §12). It provides private per-project Tailscale forwarders for Ultrathink and Agent Substrate, exact-port least-privilege ACLs for the approved VPS and admin devices (Mac mini and XPS), substrate environment cutover, and verified runtime re-entry before approved public database exposure retirement under Gate G-6.

Explicitly out of scope for Phase 2:
- Substrate data plane migrations, hypertables, and Hindsight adapter implementation (Phase 3 / n3).
- Desk Gateway implementation, OAuth AS, and seat tool rosters (Phase 4 / n4).
- Prompt assembly, marketplace plugin, and template publication (Phase 5 / n5).
- External intake and E2E acceptance drills (Phase 6 / n6).
- Final rollout synthesis and permanent retirement of `railway-app` (Phase 7 / n7).

</domain>

<decisions>
## Implementation Decisions

### Forwarder Deployment and Identity
- **D-01 (Forwarder Mapping & Listener Isolation):** Map strictly the source-authorized ports:
  - Ultrathink / production: 4000 (Greptime HTTP SQL), 4001 (Greptime gRPC), 4003 (Greptime PG wire), 5432 (TimescaleDB), 6379 (DragonflyDB). Mappings do NOT expand to unauthorized listener 4002 observed in Phase 1.
  - Agent Substrate / production: 8888 (Hindsight API REST & `/mcp/<bank>/`), 9380 (RAGFlow API), 80 (RAGFlow Web UI, explicitly optional). Mappings do NOT expand to unauthorized listener 9382 observed in Phase 1.
  - Persistence: Machine identity persists on a persistent volume mounted at `/var/lib/tailscale`.
  - Machine names: `ultrathink-production-tailscale-forwarder` and `agent-substrate-production-tailscale-forwarder`.
  - Enrollment: `tag:railway-forwarder`, key expiry disabled, auth key reusable non-ephemeral tagged. No secret auth key value enters any repository artifact or receipt.
  - `railway-app` (100.77.7.42): Retained as the observed subnet-route advertiser; not adopted as a forwarder (unproven suitability) and not retired without G-6 approval after forwarders are verified.

### Tailscale ACL & Least Privilege
- **D-02 (Exact-Port Least Privilege Matrix):**
  - Permitted devices: `tag:vps` (187.77.130.10, `100.90.229.45`), `tag:admin` (Ove's Mac mini `100.80.62.2`, XPS `100.104.90.39`).
  - Grants: EXACT mapped ports only (`tcp:4000`, `tcp:4001`, `tcp:4003`, `tcp:5432`, `tcp:6379`, `tcp:8888`, `tcp:9380`, `tcp:80`). No broad `tcp:4000-4003` range (which would permit unauthorized port 4002).
  - Deny-by-default: All other principals and all other ports denied. Forwarders cannot initiate connections to VPS or admin devices (`tag:railway-forwarder` has no outbound grants).
  - Grok Bots: Do NOT join tailnet, hold NO database credentials. Normal HTTPS egress to `desk.swcstudio.space`.
  - Team allowlist includes `desk.swcstudio.space`. Mac mini egress routing documented as INFRA-only emergency path dependent on Mac mini remaining awake.

### Multi-Device Probe Evidence
- **D-03 (Multi-Device Path Verification):**
  - Protocol-level probes for VPS (`curl` for HTTP/REST, `pg_isready` for Postgres wire, `redis-cli PING` for Dragonfly).
  - Multi-device verification: VPS, Mac mini, and XPS are distinct device paths. Mac mini probes evidenced separately from VPS. Offline status of XPS (last seen 5d ago) recorded honestly as unexercised/unverified if unreachable during probes; design approval alone is not probe evidence.

### Substrate Environment Cutover
- **D-04 (Substrate Environment Cutover & Runtime Assurance):**
  - Cutover `/etc/substrate/substrate.env` to MagicDNS forwarder hosts (`ultrathink-production-tailscale-forwarder`, `agent-substrate-production-tailscale-forwarder`).
  - Restart `substrate-mcp.service` (resolving the port 7410 collision with orphaned PID 3149064).
  - Verify `/brief` (`POST /brief`) and `events_emit` (`POST /events`) against the cutover configuration. WireGuard encryption protects plaintext service hops; Hindsight and RAGFlow bearer auth retained.

### G-6 Governed Exposure Retirement
- **D-05 (G-6 Exposure Retirement & Rollback):**
  - Removal of TimescaleDB TCP proxy (`monorail.proxy.rlwy.net:49679`) and Greptime public domain (`greptimedb-production.up.railway.app`) is an access change requiring genuine G-6 approval (`approved_by`, `approval_id`) and concrete re-create rollback plans.
  - Retirement occurs ONLY after forwarder connectivity and cutover paths are verified.
  - Rollback procedure: re-create TCP proxy on TimescaleDB, re-generate domain on GreptimeDB, restore `/etc/substrate/substrate.env` from backup.
  - `hindsight-ui` exposure kept on Railway domain only if Ove specifically requests browser access without tailnet, else Mac mini tailnet path.

### Evidence & Receipt Governance
- **D-06 (Evidence & Receipt Discipline):**
  - Publish receipt `.receipts/bot-00-programming-lead/n2-network.json` containing `tailscale status`, port probes, removal evidence, rollback, and exhaustive `unverified` list covering every unexercised path.

</decisions>

<canonical_refs>
## Canonical References

- `.planning/PROJECT.md` — fixed milestone scope, locked choices and responsibility boundaries.
- `.planning/REQUIREMENTS.md` — REQ-NETWORK-001 through REQ-NETWORK-022.
- `.planning/ROADMAP.md` — Phase 2 goal, success criteria, and source steps n2.1–n2.6.
- `.planning/intel/constraints.md` — RW-02 device scope and network constraints.
- `.planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.md` — parent-observed inventory and listener evidence.
- `.planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.json` — machine snapshot with service IDs and listener ports.
- `docs/upgrade-plan-desk-v2.md` §5 (Workstream A) and §12 (n2 delivery steps).
- `infra/railway/README.md` and `infra/railway/forwarders.yaml` — forwarder deployment procedures and mapping definitions.
- `infra/tailscale/policy.hujson` — Tailscale ACL policy definition.
- `infra/substrate/SUBSTRATE-ENV.md` — cutover configuration specification.
- `ownership.yaml` and `ci/gates/` — gate contracts and receipt requirements.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `infra/railway/forwarders.yaml` contains the exact service and port mapping table for Ultrathink and Agent Substrate.
- `infra/tailscale/policy.hujson` contains the ACL policy structure, tags, and tests.
- `/etc/substrate/substrate.env` exists on the VPS; currently points to public proxies/domains.
- `railway` CLI is installed and authenticated to workspace "Ming Chen's Projects".
- `tailscale` CLI is online on the VPS (`100.90.229.45`).

### Technical Gotchas
- `infra/tailscale/policy.hujson` on `origin/main` currently has `"tcp:4000-4003"`, which permits unauthorized port 4002. Constraint RW-02 and REQ-NETWORK-005/021 require exact-port grants (`tcp:4000`, `tcp:4001`, `tcp:4003`).
- `substrate-mcp.service` was observed failing with `error: Failed to start server. Is port 7410 in use?` due to an orphaned process (PID 3149064). Resolving this process is prerequisite to clean service restart.
- Tailscale peers: Mac mini (`100.80.62.2`) is online; XPS (`100.104.90.39`) is currently offline (last seen 5d ago). Offline status must be disclosed in unverified receipts.

</code_context>
