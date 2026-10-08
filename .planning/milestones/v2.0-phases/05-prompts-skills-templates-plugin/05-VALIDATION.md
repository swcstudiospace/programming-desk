# Phase 5: Prompts, Skills, Templates, Plugin — Validation

## Validation Checkpoints

### 1. Prompt Assembly and Placeholder Sanitization (REQ-SHARE-001..003)
- Execute `bash scripts/assemble-prompts.sh --check`.
- Verify zero literal UUIDs in `prompts/bot-0*.xml` and `prompts/_shared/core-directives.xml`.
- Verify zero unfilled placeholders in `prompts-assembled/*.xml` and `prompts/*.xml` aliases.

### 2. Prompt Sections and Discipline Verification (REQ-SHARE-004..007, REQ-SHARE-009)
- Parse all 7 seat prompt XML sources.
- Confirm presence of `<tools>`, `<memory>`, `<connectors>`, and `<routines>`.
- Confirm PD-8 external intake isolation directive in `core-directives.xml`.

### 3. Seven Core Skills Completeness (REQ-SHARE-010)
- Verify `skills/desk-bootstrap/SKILL.md`
- Verify `skills/desk-doctor/SKILL.md`
- Verify `skills/desk-gateway/SKILL.md`
- Verify `skills/hindsight-memory/SKILL.md`
- Verify `skills/ragflow-docs/SKILL.md`
- Verify `skills/platforms/railway-tailscale/SKILL.md`
- Verify `skills/tool-packs/SKILL.md`

### 4. Marketplace Plugin Packaging (REQ-SHARE-011..014)
- Validate `marketplace/swc-programming-desk/manifest.json`.
- Verify connector endpoints match `https://desk.swcstudio.space/mcp/<seat>`.
- Verify package includes all 7 core skills.

### 5. Grok Bot Team-Only Templates & Avatars (REQ-SHARE-015..022)
- Execute `python3 scripts/generate-templates.py --check`.
- Validate all 7 templates under `grokbot/templates/*.md`.
- Run Gate G-7 scanner against templates for tokens, UUIDs, or tailnet hostnames.

### 6. Bootstrap & Doctor Logic Verification (REQ-SHARE-023..038)
- Verify `desk_doctor check` and `desk_doctor repair` logic in gateway and skill.
- Verify `skills_propose` PR route and human account-UI installation boundary (REQ-SHARE-040).
- Run full gate suite (`python3 ci/gates/run_all.py`).
