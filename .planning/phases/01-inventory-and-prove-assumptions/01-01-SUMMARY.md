---
phase: 01-inventory-and-prove-assumptions
plan: 01
subsystem: kickoff-and-trackers
tags: [notion, linear, gotxcot, trackplan, double-uplift]

requires: []
provides:
  - Notion Task Graph identity reconciled (ut-muz1hdpm-2a933bcc)
  - 49 Notion rows materialized (1 Task root, 7 Node issues, 41 Step sub-issues)
  - 48 Linear issues materialized (7 Node roots, 41 Step sub-issues in Spectrum Web Co)
  - First-uplift XML preserving verbatim proposal §1 ORIGINAL block
  - Second-uplift XML binding live tracker URLs and enforcing n1-scoped dispatch boundary
affects:
  - 01-02-platform
  - 01-03-bot-client
  - 01-04-accounts-cursor
  - 01-05-s13-routing
  - 01-06-accounts-mobile
  - 01-07-accounts-hindsight

actuals:
  tokens: 2150
  tasks: 4
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Verbatim double-uplift XML formulation without lossy paraphrasing"
    - "Re-entrant tracker graph reconciliation avoiding duplicate nodes"
    - "Provider-local parent-child mappings for hierarchical issue dispatch"

key-files:
  created:
    - .receipts/bot-00-programming-lead/n1-kickoff.json
  modified: []

key-decisions:
  - "D-05: Live-URL second uplift and strict n1 dispatch boundary enforced"
  - "Preserved verbatim §1 ORIGINAL proposal block without summarization or paraphrasing"

patterns-established:
  - "Tracker materialization using real API returned IDs and URLs, never synthetic strings"
  - "Kickoff receipt capturing embedded XMLs, node/step registries, and full crosswalk"

requirements-completed:
  - REQ-INVENTORY-001
  - REQ-INVENTORY-002
  - REQ-INVENTORY-003

coverage:
  - id: D1
    description: "Reconcile Notion Task Graph identity and formulate first-uplift XML preserving verbatim proposal §1"
    requirement: REQ-INVENTORY-001
    verification:
      - kind: automated_procedural
        ref: "cat .receipts/bot-00-programming-lead/n1-kickoff.json | jq .graph_id"
        status: pass
    human_judgment: false
  - id: D2
    description: "Materialize full 7-node/41-step Notion and Linear tracker hierarchies with live IDs/URLs"
    requirement: REQ-INVENTORY-002
    verification:
      - kind: automated_procedural
        ref: "cat .receipts/bot-00-programming-lead/n1-kickoff.json | jq .materialization"
        status: pass
    human_judgment: false
  - id: D3
    description: "Formulate second-uplift XML with live tracker URLs and execute n1 dispatch boundary"
    requirement: REQ-INVENTORY-003
    verification:
      - kind: automated_procedural
        ref: "cat .receipts/bot-00-programming-lead/n1-kickoff.json | jq .dispatch_boundary"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-10-08
status: complete
---

# Phase 1 Plan 01: Tracker Graph Materialization & Kickoff Uplift Summary

**Materialized 97 live tracker rows across Notion and Linear, formulated verbatim first uplift and live-URL second uplift, and established the n1 dispatch boundary.**

## Performance

- **Duration:** 25 min
- **Tasks completed:** 4
- **Files modified/created:** 1 (`.receipts/bot-00-programming-lead/n1-kickoff.json`)

## Accomplishments

1. **Graph Identity Reconciliation:** Reconciled Notion Agent Task Graph `be3418f0-d2d8-411b-8677-fa8a95ee63be` with Graph ID `ut-muz1hdpm-2a933bcc`.
2. **First-Uplift Formulation:** Validated first-uplift XML structure preserving the verbatim proposal §1 ORIGINAL block without paraphrasing or lossy summarization.
3. **Full 7-Node / 41-Step Materialization (97 Live Rows):**
   - **Notion:** 1 Task root (`3f3bc1a0c7ae8181a56be183b865afd5`), 7 node issues parented to the Task, and 41 step sub-issues parented to their respective node issues (49 total rows).
   - **Linear:** 7 root node issues (SPE-7688 through SPE-7699) and 41 step sub-issues parented under their node issues adhering to the approved `6/6/6/6/6/6/5` distribution in team Spectrum Web Co (`c194ec01-01ec-4203-809f-37381a0392e1`).
4. **Second-Uplift & n1 Dispatch Boundary:** Formulated second-uplift XML binding all 48 live tracker URL pairs and strictly enforcing that only n1 (Inventory and prove assumptions) is dispatched.

## Verification

- Automated receipt check: Verified `.receipts/bot-00-programming-lead/n1-kickoff.json` contains complete first and second uplift XMLs, node/step registries, and verified row crosswalks.
