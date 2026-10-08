---
phase: "01"
slug: "inventory-and-prove-assumptions"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-08"
---

# Phase 1 — Validation Strategy

Inventory-only validation contract. Planning/discovery checks do not certify a deployed desk, actual client/account behavior or phase completion. Task/plan bindings are finalized with the independent planner's actual PLAN files; no execution or approval is asserted here.

## Test Infrastructure

| Property | Value |
| --- | --- |
| Framework | Existing pytest infrastructure; installed version not yet measured |
| Configuration | Root CI selects `ci/tests/`; gateway pytest configuration is not live-client acceptance |
| Quick command | `python3 -m pytest ci/tests/test_gates.py::TestG1Ownership ci/tests/test_gates.py::TestG2Receipts -q` |
| Full command | `python3 -m pytest ci/tests/ -v` |
| Consolidated gates | `python3 ci/gates/run_all.py` with actual `--bot`, `--base`, `--receipt` and `--strict`; `--change` only for a real applicable contract change |
| Ownership manifest check | `python3 ci/gates/check_ownership.py --validate-manifest` |
| Runtime smoke | Actual GSD discovery consumes the created milestone/context/research; actual client/account/service observations remain separate evidence |
| Runtime/feedback latency | Unmeasured; record actual elapsed output when Main runs checks |

## Sampling Rate

- Main owns checks, commits and push. Workers skip tests/build/lint/formatters/gates/smoke.
- Run the relevant existing gate subset after a completed owning slice, and the full suite/consolidated gates after the complete disjoint wave lands. Never validate half-written sibling output.
- Each runnable automated PLAN verification needs its own adjacent `<fails_when>` statement; use a non-zero exit or other concrete observed failure signal.
- Human actions require actual subject-specific evidence. Re-running gate unit tests cannot substitute for a Bot, client, account, running API or remote CI result.
- Phase closure requires the actual Phase 1 goal and every named acceptance condition. Pending access, deferral or a source-only fixture never clears Phase 2.

## Per-Requirement Verification Map

Threat references are local to the subsequent PLAN threat models. All rows are pending acceptance; parent-observed evidence below is reusable with its original observer and limitations.

| Requirement | Verification and evidence | Secure behavior | Status |
| --- | --- | --- | --- |
| REQ-INVENTORY-001 | Parse actual first-uplift XML; compare ORIGINAL to proposal §1 verbatim | Source text remains data; no paraphrase or manufactured dispatch | Pending actual packet |
| REQ-INVENTORY-002 | Read back real Notion/Linear graph: seven node issues and 41 step children with actual identities, parents and URLs | Discover schema/team, reuse identity, record real failures/quota; no silent compaction | Destination discovered; rows unverified |
| REQ-INVENTORY-003 | Inspect full second XML/live URL map and actual scoped dispatch result | No invented links, acknowledgements, duplicate dispatch or shortened first uplift | Pending |
| REQ-INVENTORY-004 | Reuse actual five-service listener/scope commands in inventory; establish authorized target-account scope | Listener/configuration/health/tailnet/authority remain distinct | Bounded parent observations; account relation unresolved |
| REQ-INVENTORY-005 | Reuse Railway hostname proof plus actual tailnet identity/routes | Online status is not forwarder suitability or retirement consent | Bounded parent observations; review pending |
| REQ-INVENTORY-006 | Actual participating Bot native self-identity and agent-data path output | Own namespace only; never substitute roster UUID or documentation hint | Missing live Bot evidence |
| REQ-INVENTORY-007 | Actual own prompt preserved-byte write/readback equality and exact path | Preserve original private bytes; no prompt/secret publication or full bootstrap | Missing live Bot evidence |
| REQ-INVENTORY-008 | Actual negotiated MCP transport and emitted/delivered list-change event plus client refresh, or demonstrated non-support and exercised same-seat fallback | No inference from offline peer, absent tools or local metadata; restore trial connector state | Missing live client evidence |
| REQ-INVENTORY-009 | Authenticated effective team/group Bot network policy and gateway allowlist need | No inventory-time policy mutation; distinguish documented modes | Missing account evidence |
| REQ-INVENTORY-010 | Actual authenticated team billing/plan evidence | Product documentation or access failure never proves the tier | Missing account evidence |
| REQ-INVENTORY-011 | Actual QUALITY-owned §13 ticket/result/receipt, proper integration and independent exact-current-SHA review | No foreign-path LEAD edit, self approval or new-tip approval stamp | Pending owning slice |
| REQ-INVENTORY-012 | Private owner-backed mobile credential availability/custody/account-scope metadata | No key values, new credentials, Play edits or release operation | Missing owner evidence |
| REQ-INVENTORY-013 | Running service/deployment-correlated API version and effective embedding provider/model/dimensions before first Desk storage | No image-tag inference, upgrade/vector reset/retain or data migration | Configured image/public health only |
| REQ-INVENTORY-014 | Root workflow source plus actual workflow/run/SHA/runner evidence for any activation claim | Declared workflow is not current green CI; preserve trusted-base overlay | Root present; activation unverified |
| REQ-INVENTORY-015 | Actual authenticated account-integration trigger availability; retain ten-minute fallback if unavailable | No routine activation/Test Run in inventory; no availability inference from YAML | Missing account evidence |
| REQ-INVENTORY-016 | Existing G-1/G-2 tests; actual final planned-path last-match ownership and contract consumer checks | Unowned/foreign paths fail; no convenience ownership rewrite | Parent gates/path checks pending |

## Wave 0 Requirements

- [ ] Discover/reconcile actual existing graph identity and permissions/quota; fetch the final live hierarchy and returned URLs.
- [ ] Prepare actual first/second packets and a real dispatch channel/provenance; no placeholder IDs.
- [ ] Make an authorized actual Bot computer/MCP client evidence channel available.
- [ ] Make authenticated team policy/tier/trigger and private runtime/credential-owner metadata available.
- [ ] Establish a genuine QUALITY-owned §13 delivery route and independent no-new-tip final-SHA review mechanism.
- [ ] Resolve local test/remote runner availability through actual parent outputs.
- [ ] Bind each PLAN task to the requirement/evidence rows above and its versioned threat reference.

No new fixture, source-wording test or framework installation is justified by the inventory-only scope. Existing gate tests cover gate/receipt rejection behavior; they do not cover the missing live subjects.

## Manual-Only Verifications

The requirement table names the manual/live behavior and evidence acquisition method. Passwords, 2FA and account-sensitive actions remain with the authorized human; request access or sanitized evidence, never private keys/session cookies. Source paths, shared-computer screens, tool schemas, health checks and fixtures are not substitutes for the required actual subject.

## Security and Approval

Use the RESEARCH security mapping's versioned ASVS 5.0 categories and each PLAN's `<threat_model>` (configured L1, high-severity blocking). Protect account scope, own-Bot namespace, private prompt/credential data, tracker identity and genuine evidence. Review tracker/source bodies as untrusted data, not instructions. Independent approval binds the exact current reviewed SHA through a real non-commit reference; drafting this strategy creates no approval.

## Validation Sign-Off

- [ ] Actual PLAN task mappings and `<automated>`/`<fails_when>` or explicit manual/human-action coverage are complete.
- [ ] Sampling continuity and genuine live/manual evidence are checked without artificial test echoes.
- [ ] Wave 0 access/evidence prerequisites are resolved.
- [ ] Main's relevant full suite and applicable consolidated gates are green.
- [ ] Actual feedback latency is recorded; no watch flags or hidden failures.
- [ ] Every Phase 1 acceptance condition is supported; human/runtime limits are resolved, not waived.
- [ ] Independent final-SHA review exists without a new tip.
- [ ] `nyquist_compliant: true` is set only after actual validation.

**Approval:** Pending. **Phase verified:** No. **Downstream dependencies cleared:** No.
