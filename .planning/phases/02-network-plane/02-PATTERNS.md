# Phase 2: Network plane — Pattern Map

**Mapped:** 2026-10-08  
**Files analyzed:** 8 candidate artifact and source path families.  
**Analogs found:** 5 / 8 have close tracked repository analogs; 3 GSD artifact families follow established Phase 1 patterns.  
**Status:** Pattern mapping complete; Phase 2 ready for validation planning.

## Scope and Evidence Rules

Inputs: [CONTEXT](02-CONTEXT.md), [RESEARCH](02-RESEARCH.md), `infra/railway/forwarders.yaml`, `infra/tailscale/policy.hujson`, `infra/substrate/SUBSTRATE-ENV.md`. Governed by [PROJECT](../../PROJECT.md), [REQUIREMENTS](../../REQUIREMENTS.md), [ROADMAP](../../ROADMAP.md), and [intel/constraints.md](../../intel/constraints.md).

- Cover **REQ-NETWORK-001 through REQ-NETWORK-022**: forwarder deployment/adoption, exact-port ACL policy, multi-device probing, substrate cutover, G-6 exposure retirement, and comprehensive receipt.
- `.planning/**` and `.receipts/bot-00-programming-lead/**` are LEAD-owned. `infra/**` is INFRA-owned (`bot-05-infrastructure`). Changes across seats respect ownership boundaries.
- No secrets (Tailscale auth keys, database passwords, API tokens) may enter any repository file or receipt.
- Observed vs unverified: Probes must be protocol-level commands. Offline devices (such as XPS) must be disclosed as unverified, never assumed passed.

## File Classification

`P` means `.planning/phases/02-network-plane/`.

| File Path | Role / Data Flow | Closest Tracked Analog | Match Quality |
|---|---|---|---|
| `P/02-NN-PLAN.md` | Configuration & execution specification | `.planning/phases/01-inventory-and-prove-assumptions/01-01-PLAN.md` | Exact (GSD format) |
| `P/02-VALIDATION.md` | Validation matrix & verification commands | `.planning/phases/01-inventory-and-prove-assumptions/01-VALIDATION.md` | Exact |
| `infra/tailscale/policy.hujson` | Tailscale ACL specification | Same file on `origin/main` | Exact (IaC policy) |
| `infra/railway/forwarders.yaml` | Forwarder port mapping specification | Same file on `origin/main` | Exact (config) |
| `.receipts/bot-00-programming-lead/n2-network.json` | LEAD verification receipt | `.receipts/bot-00-programming-lead/n1-platform.json` | Exact (Gate G-2 receipt) |
| `P/02-NN-SUMMARY.md` | Post-execution summary (lifecycle only) | `.planning/phases/01-inventory-and-prove-assumptions/01-01-SUMMARY.md` | Exact |
| `P/02-VERIFICATION.md` | Post-phase verification report | `.planning/phases/01-inventory-and-prove-assumptions/01-VERIFICATION.md` | Exact |
| `P/02-UAT.md` | User acceptance test record | `.planning/phases/01-inventory-and-prove-assumptions/01-UAT.md` | Exact |

## Pattern Assignments

### 1. Plan Structure (`02-NN-PLAN.md`)
Follows standard GSD format:
- YAML frontmatter: `phase`, `plan`, `type`, `wave`, `depends_on`, `files_modified`, `autonomous`, `requirements`, `user_setup`, `must_haves`.
- XML sections: `<objective>`, `<execution_context>`, `<context>`, `<tasks>`, `<threat_model>`, `<verification>`, `<success_criteria>`, `<artifacts>`, `<output>`.
- Task elements: `<task type="auto">` or `<task type="checkpoint:human-action" gate="blocking-human">` with `<name>`, `<files>`, `<read_first>`, `<action>`, `<verify>`, `<acceptance_criteria>`.

### 2. Tailscale ACL Policy (`infra/tailscale/policy.hujson`)
- Strict exact-port grants for `tag:vps` and `tag:admin` targeting `tag:railway-forwarder`.
- Test cases covering accept rules for mapped ports and deny rules for prohibited ports (e.g. 22, 443, 4002, 9382).
- Zero outbound grants for `tag:railway-forwarder`.

### 3. Verification Receipt (`.receipts/bot-00-programming-lead/n2-network.json`)
- Top-level fields: `schema_version`, `phase`, `recorded_on`, `bot`, `task_id`, `commands`, `claims`, `unverified`, `tailscale_status`, `probes`, `cutover`, `removals`, `rollback_plan`.
- Satisfies Gate G-2 (`check_receipt.py`) and G-6 (`check_rollback.py`).
