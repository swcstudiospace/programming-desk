# Phase 5: Prompts, Skills, Templates, Plugin — User Acceptance Testing (UAT)

## Checkpoint 1: Dynamic Prompt Assembly & Roster Placeholders (REQ-SHARE-001..003)
- **Test:** Run `bash scripts/assemble-prompts.sh --check` with default roster `grokbot/rosters/spectrumwebco.json`.
- **Result:** PASSED. All placeholders (`{{DESK_CHANNEL_ID}}`, `{{SEAT_UUID:<SEAT>}}`, `{{DESK_GATEWAY_URL}}`, `{{DESK_ROSTER_VERSION}}`) cleanly resolved. Zero unfilled placeholders remain in assembled XML files.

## Checkpoint 2: Prompt Discipline & Invariants (REQ-SHARE-004..007, REQ-SHARE-009)
- **Test:** Verify prompt XML sources for all 7 seats.
- **Result:** PASSED.
  - Every seat prompt carries `<tools>`, `<memory>`, `<connectors>`, and `<routines>`.
  - Refused calls are recognized as blockers, not retry loops.
  - Read tools fail open with reasons; write tools fail closed.
  - `prompts/_shared/core-directives.xml` enforces PD-8 external intake isolation (outside requests route exclusively to LEAD).
  - LEAD Phase 0 polls held handoffs before intake; `desk-held-poll` and `desk-intake-poll` codified.

## Checkpoint 3: Seven Core Skills Completeness (REQ-SHARE-008, REQ-SHARE-010, REQ-SHARE-019, REQ-SHARE-040)
- **Test:** Inspect all 7 skills in `skills/`.
- **Result:** PASSED.
  - `skills/desk-bootstrap/SKILL.md` (bootstrap procedure).
  - `skills/desk-doctor/SKILL.md` (integrity report and repair boundaries).
  - `skills/desk-gateway/SKILL.md` (tool contracts, timeout, fail-open/closed).
  - `skills/hindsight-memory/SKILL.md` (provenance, bank structure, redaction).
  - `skills/ragflow-docs/SKILL.md` (datasets, citations, chunk limits).
  - `skills/platforms/railway-tailscale/SKILL.md` (forwarders, ACLs, cutover/rollback).
  - `skills/tool-packs/SKILL.md` (app packs, 20-tool live ceiling).
  - Skill lifecycle activation is strictly human-governed via account UI (seats remain proposal-only).

## Checkpoint 4: Marketplace Plugin Manifest Packaging (REQ-SHARE-011..014)
- **Test:** Inspect `grokbot/marketplace/plugin.json`.
- **Result:** PASSED. Defines `swc-programming-desk` v1.0.0 with 7 public gateway connectors and core bundled skills.

## Checkpoint 5: Team-Only Templates & Sanitization (REQ-SHARE-015..022)
- **Test:** Run `python3 scripts/generate-templates.py --check` and scan with Gate G-7.
- **Result:** PASSED.
  - Exactly 7 templates generated under `grokbot/templates/`.
  - Excludes literal UUIDs, channel IDs, credentials, tokens, and tailnet names (`.ts.net`, `tailscale-forwarder`, `railway.internal`).
  - Routines set to `paused until desk_doctor check is green`.
  - Avatars bound to `grokbot/avatars/<seat>.png`.

## Checkpoint 6: Bootstrap Procedure & Doctor Reporting (REQ-SHARE-023..039)
- **Test:** Verify `desk_doctor check` and `repair` logic against gateway implementation and Gate G-7.
- **Result:** PASSED.
  - 7-step bootstrap verified.
  - All 7 doctor checks (prompt hash, skills, memory, tools, connector, roster, substrate) enforced.
  - `repair` strictly bounded to prompt reinstallation and connector re-auth.
  - G-7 integrity scan cleanly passes across all 7 rosters, 8 packs, 22 prompt files, and 7 templates.
