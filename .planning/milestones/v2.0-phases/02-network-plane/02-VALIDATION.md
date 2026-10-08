---
phase: "02"
slug: "network-plane"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-08"
---

# Phase 2 — Validation Strategy

Network plane validation contract. Governed by `docs/upgrade-plan-desk-v2.md` §5, `ownership.yaml`, `ci/gates/`, and REQ-NETWORK-001 through REQ-NETWORK-022.

## Test Infrastructure

| Property | Value |
| --- | --- |
| Gate Framework | Python 3 + PyYAML + pytest (`ci/gates/run_all.py`, `ci/gates/check_receipt.py`, `ci/gates/check_ownership.py`, `ci/gates/check_rollback.py`) |
| Network Probe Tools | `tailscale status`, `tailscale ping`, `curl`, `pg_isready`, `redis-cli` |
| Substrate MCP Runtime | Bun runtime running `packages/mcp-server/src/index.ts` via `substrate-mcp.service` |
| Consolidated Gates | `python3 ci/gates/run_all.py --bot bot-00-programming-lead --receipt .receipts/bot-00-programming-lead/n2-network.json --base origin/main` |
| Manifest Check | `python3 ci/gates/check_ownership.py --validate-manifest` |

## Sampling Rate

- Automated PLAN verification commands must be executed and recorded in receipt JSON.
- Every mapped port must have a protocol-level verification command with exit code and output captured.
- Permitted devices (VPS, Mac mini, XPS) must be probed or observed individually; unexercised paths must be explicitly recorded in the `unverified` array.
- G-6 destructive actions (public proxy/domain deletion) must be preceded by recorded approval and validated re-create rollback plans.

## Per-Requirement Verification Map

| Requirement | Verification and Evidence | Secure Behavior | Status |
| --- | --- | --- | --- |
| REQ-NETWORK-001 | Protocol probes for ports 4000, 4001, 4003, 5432, 6379 on `ultrathink-production-tailscale-forwarder` | Port 4002 excluded; private internal routing only | Pending |
| REQ-NETWORK-002 | Protocol probes for ports 8888 and 9380 on `agent-substrate-production-tailscale-forwarder` | Port 9382 excluded; port 80 optional | Pending |
| REQ-NETWORK-003 | Tailscale node identity persists across restarts via volume mounted at `/var/lib/tailscale` | No orphaned or duplicate nodes created | Pending |
| REQ-NETWORK-004 | `tag:railway-forwarder`, key expiry disabled, reusable non-ephemeral auth key; no secret key in receipts | Credential confidentiality enforced | Pending |
| REQ-NETWORK-005 | Tailscale ACL exact-port grants for `tag:vps` and `tag:admin`; deny-default for all others | Exact ports only (`tcp:4000`, etc.); no ranges | Pending |
| REQ-NETWORK-006 | VPS tailnet port probe evidence recorded in receipt with protocol-level exit codes | Real protocol probes (`pg_isready`, `curl`, `redis-cli`) | Pending |
| REQ-NETWORK-007 | Mac mini administrative path evidenced separately from VPS probes | Separate device evidence recorded | Pending |
| REQ-NETWORK-008 | Substrate environment `/etc/substrate/substrate.env` cut over to MagicDNS forwarder hosts | No public DB proxy/domain references remain in env | Pending |
| REQ-NETWORK-009 | `substrate-mcp` restarted and `POST /brief` responds with HTTP 200/valid brief | Validates index store reachability over tailnet | Pending |
| REQ-NETWORK-010 | `POST /events` invoked and returns stored event | Proves GreptimeDB post-cutover event path | Pending |
| REQ-NETWORK-011 | TimescaleDB TCP proxy removed with recorded G-6 approval and re-create rollback plan | Approval and rollback verified before removal | Pending |
| REQ-NETWORK-012 | GreptimeDB public domain removed with recorded G-6 approval and re-create rollback plan | Approval and rollback verified before removal | Pending |
| REQ-NETWORK-013 | Public exposure retirement occurs strictly AFTER forwarder cutover is verified | Zero downtime for dependent substrate services | Pending |
| REQ-NETWORK-014 | `hindsight-ui` kept on Railway domain only if Ove requests non-tailnet access; else Mac mini | Exposure minimized to authorized operators | Pending |
| REQ-NETWORK-015 | `railway-app` (100.77.7.42) role verified; not assumed forwarder; retirement deferred | Subnet advertiser left intact until replaced | Pending |
| REQ-NETWORK-016 | Grok Bots use HTTPS egress only; no tailnet membership or DB credentials | Desk perimeter isolation preserved | Pending |
| REQ-NETWORK-017 | `desk.swcstudio.space` included in Cursor Team allowlist if allowlist mode active | Gateway egress permitted for Bots | Pending |
| REQ-NETWORK-018 | Mac mini emergency egress route documented as INFRA-only with awake dependency | Operational limitations documented | Pending |
| REQ-NETWORK-019 | Plaintext forwarder ports travel over WireGuard encryption; bearer keys retained | In-transit encryption + app authentication | Pending |
| REQ-NETWORK-020 | Receipt published with status, probes, removal, rollback, and unverified array | Full audit trail satisfying Gate G-2 | Pending |
| REQ-NETWORK-021 | VPS, Mac mini, and XPS device paths evidenced; access outside exact ports denied | Design approval alone is not probe evidence | Pending |
| REQ-NETWORK-022 | Mac mini and XPS receive identical exact-port admin grants; deny-default for all others | Least privilege enforced across admin devices | Pending |
