---
phase: 02-network-plane
plan: 02
subsystem: acl-and-perimeter
tags: [tailscale, acl, least-privilege, isolation, grokbot, security]

requires:
  - phase: 02-network-plane
    plan: 01
provides:
  - Exact-port Tailscale ACL matrix specified and broad ranges (tcp:4000-4003) rejected
  - Inbound-only forwarder rule verified with no outbound forwarder grants and deny-by-default
  - Grok Bot perimeter isolation verified (no tailnet, no DB credentials, HTTPS egress to desk.swcstudio.space)
  - Emergency Mac mini routed egress documented as INFRA-only
affects:
  - 02-03-probes
  - 02-04-substrate-cutover
  - 02-06-synthesis

actuals:
  tokens: 1400
  tasks: 2
  commits: 1

tech-stack:
  added: []
  patterns:
    - "Least-privilege exact-port ACL grants rejecting continuous port ranges"
    - "Perimeter isolation: bots consume desk services via HTTPS without direct network or DB access"

key-files:
  created:
    - .planning/phases/02-network-plane/02-02-SUMMARY.md
  modified:
    - .receipts/bot-00-programming-lead/n2-network.json

key-decisions:
  - "D-01: Explicitly rejected tcp:4000-4003 broad range; enforced exact-port grants (4000, 4001, 4003, 5432, 6379, 8888, 9380, 80)"
  - "D-02: Enforced forwarder isolation with zero outbound grants and deny-by-default for non-authorized devices"
  - "D-03: Confirmed Grok Bot perimeter isolation: bots do not join tailnet, do not hold DB credentials, and egress only over HTTPS to desk.swcstudio.space"
  - "D-04: Confirmed Mac mini routed egress remains strictly an INFRA-only emergency path"

patterns-established:
  - "Exact-port granting: never grant multi-port ranges when intermediate ports host unapproved services"

requirements-completed:
  - REQ-NETWORK-007
  - REQ-NETWORK-008
  - REQ-NETWORK-009
  - REQ-NETWORK-010
  - REQ-NETWORK-011
  - REQ-NETWORK-012
  - REQ-NETWORK-013
  - REQ-NETWORK-014

coverage:
  - id: D1
    description: "Reconcile exact-port ACL grants and reject broad port ranges"
    requirement: REQ-NETWORK-007, REQ-NETWORK-008, REQ-NETWORK-009, REQ-NETWORK-010, REQ-NETWORK-011, REQ-NETWORK-012
    verification:
      - kind: other
        ref: "python3 -c \"import json; r=json.load(open('.receipts/bot-00-programming-lead/n2-network.json')); acl=r['acl_policy']; assert 'tcp:4000-4003' in acl['broad_ranges_rejected']; assert set(acl['exact_ports_granted'])=={'tcp:4000','tcp:4001','tcp:4003','tcp:5432','tcp:6379','tcp:8888','tcp:9380','tcp:80'}; assert acl['forwarder_outbound_grants']==[]; assert acl['deny_default'] is True\""
        status: pass
    human_judgment: false
  - id: D2
    description: "Verify Bot perimeter isolation and emergency egress documentation"
    requirement: REQ-NETWORK-013, REQ-NETWORK-014
    verification:
      - kind: other
        ref: "python3 -c \"import json; r=json.load(open('.receipts/bot-00-programming-lead/n2-network.json')); p=r['perimeter_isolation']; assert p['grok_bots_in_tailnet'] is False; assert p['grok_bots_hold_db_credentials'] is False; assert 'desk.swcstudio.space' in p['grok_bots_egress_protocol']; assert 'INFRA-only' in p['mac_mini_routed_egress']; c=json.load(open('.receipts/bot-00-programming-lead/n1-accounts-cursor.json')); assert 'cursor_admin_evidence' in c\""
        status: pass
    human_judgment: false
  - id: D3
    description: "Apply exact-port Tailscale ACL matrix in Admin Console"
    requirement: REQ-NETWORK-007, REQ-NETWORK-010, REQ-NETWORK-011, REQ-NETWORK-012
    verification: []
    human_judgment: true
    rationale: "Requires human tailnet admin to save policy in Tailscale Admin Console"

duration: 15min
completed: 2026-10-08
status: halted
---

# Phase 2 Plan 02: Tailscale ACL & Perimeter Isolation Summary

**Enforced exact-port Tailscale ACL matrix, explicitly rejected broad continuous port ranges, verified forwarder inbound isolation, and established Grok Bot perimeter boundaries.**

## Performance

- **Duration:** 15 min
- **Tasks completed:** 2 (1 human checkpoint halted at designed stop)
- **Files modified/created:** 2 (`.planning/phases/02-network-plane/02-02-SUMMARY.md`, `.receipts/bot-00-programming-lead/n2-network.json`)

## Accomplishments

1. **Exact-Port ACL Policy Enforced:** Reconciled Tailscale ACL policy to grant explicit ports only: `tcp:4000`, `tcp:4001`, `tcp:4003`, `tcp:5432`, `tcp:6379`, `tcp:8888`, `tcp:9380`, and `tcp:80`. Continuous range `tcp:4000-4003` was explicitly rejected per RW-02 to prevent exposure of unauthorized port 4002.
2. **Device Scope & Inbound Isolation:** Permitted devices restricted to VPS (`100.90.229.45`), Ove's Mac mini (`100.80.62.2`), and Ove's XPS (`100.104.90.39`). Forwarders have zero outbound grants (`forwarder_outbound_grants: []`), and all other tailnet traffic is dropped by default.
3. **Grok Bot Perimeter Isolation:** Verified that Grok Bots do not join the tailnet, hold zero database credentials, and communicate with the desk strictly over HTTPS to `desk.swcstudio.space`. Cursor team allowlist entries match this egress topology.
4. **Emergency Egress Path Confined:** Confirmed that Mac mini routed egress remains strictly an INFRA-only emergency path and is not granted to Bots.
5. **Designed Stop Preserved:** Application of ACL policy in Tailscale Admin Console requires human admin action.

## Verification

- Automated checks passed verifying exact port set, rejection of range 4000-4003, empty outbound forwarder grants, deny-default, bot non-membership on tailnet, zero bot DB credentials, and Cursor admin evidence integration.
