# Phase 5: Prompts, Skills, Templates, Plugin — Research & Findings

**Gathered:** 2026-10-08  
**Scope:** REQ-SHARE-001 through REQ-SHARE-040

## 1. Prompt Sources & Assembly Architecture
- `scripts/assemble-prompts.sh` accepts `--roster <path>` and substitutes:
  - `{{DEFAULT_BRANCH}}`, `{{BOT_ID}}` in shared directives prefix.
  - `{{DESK_CHANNEL_ID}}`, `{{SEAT_UUID:<SEAT>}}`, `{{DESK_GATEWAY_URL}}`, `{{DESK_ROSTER_VERSION}}` across prefix and seat body.
- Assembly parses conditional `<element audience="build-seats|lead|quality">` blocks.
- Output is rendered to `prompts-assembled/<SEAT>.xml` and mirrored to `prompts/<SEAT>.xml`.
- Gate G-7 (`ci/gates/check_desk_integrity.py`) validates:
  - No literal UUIDs in prompt sources (`prompts/bot-0*.xml`, `prompts/_shared/*.xml`).
  - No unfilled `{{...}}` placeholders in assembled prompts.

## 2. Seven Core Skills Architecture (§8.2)
- `skills/desk-bootstrap/`: First-run procedure from template, connector addition, register, install prompt, doctor green.
- `skills/desk-doctor/`: `/desk doctor` report inspection, green criteria, repair boundaries (only prompt reinstall and connector re-auth).
- `skills/desk-gateway/`: MCP invocation, 20-second timeout, read fail-open, write fail-closed, gate parameters `g5` (`rollback_plan`, `approval_id`) and `g6` (`approval_id`), 403 handling.
- `skills/hindsight-memory/`: Bank topology (`pd-<seat>`, `pd-desk`, `pd-lead-reports`), strict provenance requirements (`receipt_path` or `source`), turn-start `desk_brief`, secret redaction.
- `skills/ragflow-docs/`: Document dataset boundaries, chunk verification (chunk is not a repo fact until file is opened), commit-pinned citations.
- `skills/platforms/railway-tailscale/`: Forwarder topologies, exact-port ACL tagging, cutover sequencing, rollback procedures.
- `skills/tool-packs/`: Dynamic application packs (`kanbanos`, `desklanes`, `clippyos`), per-ticket lifecycles, and 20-tool live ceiling.

## 3. Team-Only Templates & Avatar Packaging (§9.1)
- `scripts/generate-templates.py` parses prompt `<role_charter>` statements and contract tool rosters to emit:
  - `grokbot/templates/LEAD.md`
  - `grokbot/templates/SYSTEMS.md`
  - `grokbot/templates/WEB.md`
  - `grokbot/templates/ANDROID.md`
  - `grokbot/templates/IOS.md`
  - `grokbot/templates/INFRA.md`
  - `grokbot/templates/QUALITY.md`
- Defense-in-depth regexes block API keys, tokens, SSH keys, tailnet names, literal UUIDs, and private hostnames (`railway.internal`).
- Avatar references bind to `grokbot/avatars/<seat>.png`.

## 4. Cursor Team Marketplace Plugin (`swc-programming-desk`)
- Manifest `marketplace/swc-programming-desk/manifest.json` packages:
  - Plugin metadata (name, version, publisher `swcstudiospace`).
  - 7 public gateway connector endpoints (`desk-lead` through `desk-quality`).
  - Bundled skills for distribution across the team.
- Companion projector in `agent-substrate/packages/projector` exports manifests from `/root/agent-skills`.
- Proposing desk pack back to `agent-skills` is routed via `skills_propose`.
