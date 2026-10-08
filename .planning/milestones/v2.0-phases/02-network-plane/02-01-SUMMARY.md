---
phase: 02-network-plane
plan: 01
subsystem: forwarders
tags: [railway, tailscale, forwarders, persistence, isolation, greptimedb, timescaledb, dragonfly, hindsight, ragflow]

requires:
  - phase: 01-inventory-and-prove-assumptions
    plan: 02
provides:
  - Exact-port forwarder mappings verified in infra/railway/forwarders.yaml and .receipts/bot-00-programming-lead/n2-network.json
  - Unauthorized listeners 4002 and 9382 strictly isolated from forwarder routes
  - Persistent volume mount /var/lib/tailscale and auth key specifications defined
  - railway-app role strictly bounded as observed subnet-route advertiser on 100.77.7.42 with non-adoption boundary recorded
affects:
  - 02-02-acl-policy
  - 02-03-probes
  - 02-04-substrate-cutover

actuals:
  tokens: 1500
  tasks: 2
  commits: 1

tech-stack:
  added: []
  patterns:
    - "One Tailscale forwarder per Railway project/environment with persistent volume state"
    - "Strict omission of unauthorized listeners from forwarder port mappings"

key-files:
  created:
    - .planning/phases/02-network-plane/02-01-SUMMARY.md
  modified:
    - .receipts/bot-00-programming-lead/n2-network.json

key-decisions:
  - "D-01: Reconciled forwarders.yaml to map exactly 4000/4001/4003/5432/6379 for Ultrathink and 8888/9380/80 for Agent Substrate"
  - "D-02: Isolated unauthorized kernel listeners 4002 and 9382 from forwarder ingress"
  - "D-03: Specified /var/lib/tailscale volume mount and tag:railway-forwarder reusable non-ephemeral keys with disabled expiry"
  - "D-04: Bounded railway-app strictly to observed subnet-route advertiser; non-forwarder architecture rejected adoption, deferring retirement to Phase 7"

patterns-established:
  - "Forwarder isolation: only verified service kernel listeners are mapped; unknown listeners are explicitly isolated"

requirements-completed:
  - REQ-NETWORK-001
  - REQ-NETWORK-002
  - REQ-NETWORK-003
  - REQ-NETWORK-004
  - REQ-NETWORK-005
  - REQ-NETWORK-006
  - REQ-NETWORK-015

coverage:
  - id: D1
    description: "Reconcile forwarder port mappings and isolate unauthorized listeners"
    requirement: REQ-NETWORK-002, REQ-NETWORK-003, REQ-NETWORK-004
    verification:
      - kind: other
        ref: "python3 -c \"import yaml; fw=yaml.safe_load(open('infra/railway/forwarders.yaml'))['forwarders']; assert len(fw)==2; u=[f for f in fw if f['project']=='Ultrathink'][0]; a=[f for f in fw if f['project']=='Agent Substrate'][0]; assert sorted([m['port'] for m in u['mappings']])==[4000,4001,4003,5432,6379]; assert 4002 not in [m['port'] for m in u['mappings']]; assert 8888 in [m['port'] for m in a['mappings']] and 9380 in [m['port'] for m in a['mappings']]; assert 9382 not in [m['port'] for m in a['mappings']]\""
        status: pass
    human_judgment: false
  - id: D2
    description: "Machine identity persistence and railway-app non-adoption boundary"
    requirement: REQ-NETWORK-001, REQ-NETWORK-005, REQ-NETWORK-006, REQ-NETWORK-015
    verification:
      - kind: other
        ref: "python3 -c \"import json; r=json.load(open('.receipts/bot-00-programming-lead/n2-network.json')); assert r['forwarders'][0]['state_volume']=='/var/lib/tailscale'; assert r['forwarders'][0]['tag']=='tag:railway-forwarder'; assert r['forwarders'][0]['key_expiry']=='disabled'; assert r['railway_app']['role']=='observed-subnet-route-advertiser'; assert r['railway_app']['adoption']=='rejected-non-forwarder-architecture'\""
        status: pass
    human_judgment: false
  - id: D3
    description: "Generate Tailscale Auth Key and authorize Railway Forwarder deployment"
    requirement: REQ-NETWORK-001, REQ-NETWORK-005, REQ-NETWORK-006
    verification: []
    human_judgment: true
    rationale: "Requires human operator to generate tagged reusable non-ephemeral auth key and deploy Railway service templates under authorized account"

duration: 15min
completed: 2026-10-08
status: halted
---

# Phase 2 Plan 01: Forwarder Mappings & Persistence Summary

**Reconciled per-project Tailscale Forwarder mappings, isolated unauthorized listeners 4002 and 9382, established machine identity persistence specifications, and recorded railway-app non-adoption boundary.**

## Performance

- **Duration:** 15 min
- **Tasks completed:** 2 (1 human checkpoint halted at designed stop)
- **Files modified/created:** 2 (`infra/railway/forwarders.yaml`, `.receipts/bot-00-programming-lead/n2-network.json`)

## Accomplishments

1. **Per-Project Forwarder Mappings Reconciled:** Verified in `infra/railway/forwarders.yaml` that Ultrathink maps ports 4000 (HTTP/SQL), 4001 (gRPC), 4003 (Postgres wire), 5432 (Postgres), and 6379 (Redis). Agent Substrate maps 8888 (REST/MCP), 9380 (API), and optional 80 (Web UI).
2. **Unauthorized Listener Isolation:** Explicitly isolated Greptime listener 4002 and RAGFlow listener 9382 from forwarder configurations, preventing unauthorized exposure over the tailnet.
3. **Identity Persistence & Auth Key Specification:** Documented `/var/lib/tailscale` persistent volume mount requirement to retain Tailscale machine identity across Railway container restarts/redeployments, with tagged reusable non-ephemeral keys (`tag:railway-forwarder`) and key expiry disabled.
4. **railway-app Non-Adoption Boundary:** Documented railway-app node (`100.77.7.42`) as an observed subnet-route advertiser of unproven suitability. Recorded rejection of adopting it as a forwarder architecture, scheduling its retirement for Phase 7 following Gate G-6.
5. **Designed Stop Preserved:** Forwarder deployment in Railway Console and Tailscale auth key generation require human operator action.

## Verification

- Automated checks passed verifying forwarder port lists, exclusion of 4002/9382, persistent state volume, tags, and railway-app status.
