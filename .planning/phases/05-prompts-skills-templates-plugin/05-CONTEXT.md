# Phase 5: Prompts, Skills, Templates, Plugin — Context

**Gathered:** 2026-10-08  
**Status:** In Progress / Execution  
**Mode:** Autonomous orchestration. Governed by `docs/upgrade-plan-desk-v2.md` §8, §9, `ownership.yaml`, `docs/desk-operating-model.md`, and REQ-SHARE-001 through REQ-SHARE-040.

<domain>
## Phase Boundary

Phase 5 delivers Workstream E (Grok Bot share: install the desk from Add Bot) and source step n5 (`docs/upgrade-plan-desk-v2.md` §8, §9, §11, §12). It establishes:
1. Dynamic prompt assembly (`scripts/assemble-prompts.sh`) with placeholders (`{{DESK_CHANNEL_ID}}`, `{{SEAT_UUID:<SEAT>}}`, `{{DESK_GATEWAY_URL}}`, `{{DESK_ROSTER_VERSION}}`) and committed team roster (`grokbot/rosters/spectrumwebco.json`).
2. Seat prompt upgrades v1.1 across all 7 seats (`<tools>`, `<memory>`, `<connectors>`, `<routines>`), PD-8 outside intake isolation in `prompts/_shared/core-directives.xml`.
3. 7 comprehensive new skills in `skills/`:
   - `skills/desk-bootstrap/SKILL.md`
   - `skills/desk-doctor/SKILL.md`
   - `skills/desk-gateway/SKILL.md`
   - `skills/hindsight-memory/SKILL.md`
   - `skills/ragflow-docs/SKILL.md`
   - `skills/platforms/railway-tailscale/SKILL.md`
   - `skills/tool-packs/SKILL.md`
4. Marketplace packaging: Cursor team marketplace plugin `swc-programming-desk` manifest (`marketplace/swc-programming-desk/manifest.json`), seven public gateway connector definitions (`desk-lead` through `desk-quality`), and the companion `grok-bot` projector in `agent-substrate`.
5. 7 Grok Bot Team-only templates (`grokbot/templates/*.md`), seat avatars (`grokbot/avatars/`), and exclusion enforcement (zero tokens, passwords, literal UUIDs, or tailnet hostnames).
6. Bootstrap procedure (`/desk bootstrap`) and `desk-doctor check` verification suite with honest disclosures for external UI publication.

Explicitly out of scope for Phase 5:
- Live fresh human user acceptance drills and mobile iOS approval tests (Phase 6 / n6).
- Final cutover execution, public endpoint tear-down, and railway-app node retirement (Phase 7 / n7).

</domain>

<decisions>
## Implementation Decisions

### 1. Placeholders and Dynamic Assembly
- **D-01 (Strict Placeholder Substitution):** Prompts must never contain literal UUIDs or channel IDs. Placeholders `{{DESK_CHANNEL_ID}}`, `{{SEAT_UUID:<SEAT>}}`, `{{DESK_GATEWAY_URL}}`, and `{{DESK_ROSTER_VERSION}}` are resolved at assembly time. `scripts/assemble-prompts.sh` strictly refuses any output with remaining `{{...}}` tokens.
- **D-02 (Roster Registry):** `grokbot/rosters/spectrumwebco.json` is committed as the default team roster. Non-secret addressing IDs (UUIDs and channel IDs) are valid in roster JSON; credentials and tokens are forbidden.

### 2. Prompt Sections & Policy
- **D-03 (Seat Prompt Invariants):** Each seat source defines `<tools>`, `<memory>`, `<connectors>`, and `<routines>`. Unlisted tools do not exist; refused calls fail closed without retry loops. Read tools fail open with reasons. Gated tools `g5`/`g6` require approval/rollback metadata.
- **D-04 (PD-8 Outside Intake Isolation):** External intake is routed exclusively through LEAD via `desk_intake_next`/`desk_intake_ack` or Ove 1:1. Build seats and QUALITY holding non-LEAD requests emit held handoffs (priority false) and never execute outside tasks directly.
- **D-05 (Always-Loaded Skills):** `verification-receipts`, `desk-doctor`, `desk-bootstrap`, and `desk-production-loop` form the core invariant skill set for all desk seats.

### 3. Marketplace Plugin & Shared Library
- **D-06 (Plugin Packaging):** `marketplace/swc-programming-desk/manifest.json` packages the 7 gateway connectors and 7 core desk skills for Cursor Team Marketplace distribution.
- **D-07 (Projector Target & Proposal Boundary):** The desk pack proposal is routed to `agent-skills` via `skills_propose`. Live account-UI activation and template publishing remain authorized human actions; unactivated templates/manifests are recorded in `unverified`.

### 4. Grok Bot Team-Only Templates & Doctor
- **D-08 (Template Exclusions):** Generated under `grokbot/templates/<SEAT>.md` via `scripts/generate-templates.py`. Carries only name, permanent rules (charter), enabled skills, paused routines, and avatar. Absolutely zero credentials, tokens, literal UUIDs, or tailnet hostnames.
- **D-09 (Doctor Semantics):** `desk_doctor check` proves prompt SHA, skill presence, memory bank health, tool rosters, connector isolation (403 on wrong seat), group roster, and substrate event/doc health. `repair` only reinstalls prompts and triggers re-auth; it never weakens gates or edits receipts.
</decisions>
