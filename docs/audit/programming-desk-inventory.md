# Programming Desk Inventory Audit (n3)

**Issue:** SPE-5545  
**Repo:** /root/src/repos/programming-desk  
**Date:** 2026-09-30 (re-ran all commands)  
**Scope:** Follow n3 spec steps exactly. No source edits. Evidence from direct ls/find/grep/read. Disjoint from n2. Assumptions: defer self-improve, user-facing tools, snapshot.

## 1. Layout (from ls -la and find -maxdepth 3 -type d)

Re-ran:
```
ls -la /root/src/repos/programming-desk
find . -maxdepth 3 -type d ! -path './.git*' | sort
```

Top-level (ls -la):
```
drwxr-xr-x  18 root root  4096 Sep 30 02:00 .
...
-rw-r--r--   1 root root  9731 Sep 29 23:01 README.md
drwxr-xr-x   6 root root  4096 Sep 29 23:01 ci
drwxr-xr-x   6 root root  4096 Sep 30 06:36 contracts
drwxr-xr-x   2 root root  4096 Sep 30 01:55 docs
drwxr-xr-x   5 root root  4096 Sep 30 02:00 grokbot
drwxr-xr-x   6 root root  4096 Sep 30 02:00 infra
-rw-r--r--   1 root root 13487 Sep 30 01:52 ownership.yaml
drwxr-xr-x   3 root root  4096 Sep 30 01:59 prompts
drwxr-xr-x   2 root root  4096 Sep 29 23:01 prompts-assembled
drwxr-xr-x   2 root root  4096 Sep 30 02:00 scripts
drwxr-xr-x   3 root root  4096 Sep 30 01:58 services
drwxr-xr-x  17 root root  4096 Sep 30 02:00 skills
drwxr-xr-x   3 root root  4096 Sep 29 23:01 vendor
drwxr-xr-x   4 root root  4096 Sep 30 06:29 web
```

High-level dirs (find maxdepth 3, sample):
```
.
./.receipts
./.receipts/bot-00-programming-lead
./.receipts/bot-01-systems-backend
...
./ci
./ci/.github
./ci/.github/workflows
./ci/gates
./ci/hooks
./ci/tests
./contracts
./contracts/changes
./contracts/events
./contracts/tool-packs
./contracts/tool-rosters
./docs
./grokbot
./grokbot/avatars
./grokbot/rosters
./grokbot/templates
./infra
./infra/desk-gateway
./infra/railway
./infra/tailscale
./infra/unified-lsp-broker
./prompts
./prompts-assembled
./prompts/_shared
./scripts
./services
./services/desk-gateway
./services/desk-gateway/src
./services/desk-gateway/tests
./skills
./skills/code-review
./skills/contract-first-changes
./skills/debugging
./skills/desk-bootstrap
./skills/desk-doctor
./skills/desk-gateway
./skills/gotxcot-uplift
./skills/greptile-merge-gate
./skills/hindsight-memory
./skills/platforms
./skills/platforms/android
...
./skills/tool-packs
./skills/verification-receipts
./vendor
./web
./web/desk3d
./web/mcp-unified-lsp
```

Key files read first (step 2):
- README.md
- ARCHITECTURE.md
- docs/desk-operating-model.md
- docs/quality-gates.md
- docs/cross-bot-protocol.md
- docs/github-sot-orchestration.md
- docs/handoff-contracts.md
- docs/upgrade-plan-desk-v2.md
- grokbot/README.md
- skills/README.md
- contracts/README.md
- ownership.yaml

Also read sub-READMEs, scripts, contracts, prompts, templates.

## 2. Instructions format + tool ref

Instructions live in XML prompts (system prompt for seats).

Format (from prompts/_shared/core-directives.xml + prompts/bot-*.xml):
- XML root: `<agent id="bot-0N-..." version="1.1" ...>`
- Sections: `<identity>`, `<mission>`, `<desk_roster>`, `<owned_paths>`, `<does_not_own>`, `<skills>`, `<tools contract="..." gateway="...">`, `<memory>`, `<connectors>`, `<routines>` (LEAD), role-specific like `<lead_pre_dispatch_check>`, etc.
- Core prepended: `prompts/_shared/core-directives.xml` (prime_directives, verification_discipline, ownership_rules, skill_loading, etc.).
- Assembled at runtime: `prompts-assembled/<SEAT>.xml` or aliases `prompts/LEAD.xml` etc. (via scripts/assemble-prompts.sh).
- Substituted placeholders from roster: `{{DESK_CHANNEL_ID}}`, `{{SEAT_UUID:LEAD}}`, `{{DESK_GATEWAY_URL}}`, `{{DESK_ROSTER_VERSION}}`.
- At runtime on Grok Bot: written to `/home/box/agent-data/agents/<uuid>/SYSTEM_PROMPT.xml` (per ARCHITECTURE.md, upgrade-plan §8.1, desk-bootstrap).

Tool ref:
- `<tools contract="contracts/tool-rosters/<short>.yaml" gateway=".../mcp/<seat>">`
- Lists `<tool name="..." kind="read|write"/>` + rules.
- Contracts in `contracts/tool-rosters/*.yaml` (version, seat, endpoint, tools[] with name/kind/gates/description/backend/input JSON schema).
- Core 8 tools always (desk_brief, desk_docs_search, desk_memory_*, desk_ownership_resolve, desk_receipt_check, desk_event_emit, desk_doctor).
- Per-seat + packs (tool-packs for mobile/WEB, <=5 extra, <=20 live).
- G-7 enforces 10-15 (or <=20 w/ pack), schemas, g5/g6 fields.
- Evidence: contracts/tool-rosters/lead.yaml (read), prompts/bot-00-programming-lead.xml (read), contracts/tool-rosters/*.yaml, upgrade-plan §7.

Example from lead prompt:
```xml
<tools contract="contracts/tool-rosters/lead.yaml" gateway="{{DESK_GATEWAY_URL}}/mcp/lead">
  <tool name="desk_brief" kind="read"/>
  ...
  <rule>A tool the gateway did not list does not exist.</rule>
</tools>
```

## 3. Skill format

Skills: progressive L1/L2/L3 in `skills/<name>/SKILL.md` (and subdirs for platforms).

Format (from skills/README.md, multiple SKILL.md reads):
- YAML frontmatter:
  ```
  ---
  name: <name>
  description: ...
  bots: [all | lead | ...]
  gates: [G-2 | ...]
  ---
  ```
- `# Title`
- `## L1 — Summary` (or "When this applies (L1)"): decision tree, when to load.
- `## L2 — Method` (or "Method (L2)"): procedures, rubrics, tables, worked examples, failure modes.
- `## L3 — References` (optional, in references/ or inline).
- Cite levels in decisions. "Add when mistake twice".
- Always-loaded vs on_demand / on_intake in prompt `<skill path="skills/..." load="always">`.
- In doctor: match to `/` composer list in Grok Bot private skills library.
- Examples read: skills/verification-receipts/SKILL.md, skills/desk-bootstrap/SKILL.md, skills/desk-doctor/SKILL.md, skills/trackplan-dispatch/SKILL.md, skills/platforms/* /SKILL.md.

From desk-bootstrap (L1 decision tree + L2 steps + worked example + gates):
- References gates (G-7).
- No duplication with core-directives.

## 4. Event Hook format

In Grok Bot context: "Routines" (in templates and prompts).

Format:
- In `grokbot/templates/<SEAT>.md` (generated):
  ```
  ## Routines

  - <routine-name> — <description> — paused until desk_doctor check is green
  ```
- LEAD: `desk-held-poll`, `desk-intake-poll` (every 10 min or GitHub label).
- Seats: `desk-heartbeat` (daily `desk_brief`).
- In XML prompts (LEAD): `<routines>` section listing them.
- In doctor/bootstrap: paused until green; un-paused by LEAD after all seats doctor green.
- Related: Grok platform "Routines: 50 per Bot, event triggers via Cursor integrations (GitHub, Slack)".
- Not shell hooks (ci/hooks/ are pre-commit for G-3).

Evidence: grokbot/templates/LEAD.md (read), all templates, upgrade-plan-desk-v2.md §8.1/9.2/9.3 (read), prompts/bot-00-....xml, skills/desk-doctor/SKILL.md.

## 5. Example bot template (path)

Example: `grokbot/templates/LEAD.md` (full read; one of 7 generated).

Cited by path: `grokbot/templates/LEAD.md`

Content summary (verified):
```
# Programming Lead (LEAD)

Grok Bot Team-only template for the LEAD seat. Generated by scripts/generate-templates.py from prompts/bot-00-programming-lead.xml and contracts/tool-rosters/lead.yaml; do not hand-edit. Share -> Create template -> Team-only. ...

## Name
Programming Lead (LEAD)

## Description
... (role charter statements from prompt)
First run: /desk bootstrap
Gateway: https://desk.swcstudio.space/mcp/lead

## Enabled skills
- desk-bootstrap
- desk-doctor
- verification-receipts
- ...

## Routines
- desk-held-poll — every 10 minutes: ...
- desk-intake-poll — ...

## Avatar
Avatar: grokbot/avatars/lead.png
```

Other templates: SYSTEMS.md, WEB.md, ANDROID.md, IOS.md, INFRA.md, QUALITY.md (all in grokbot/templates/).

Generated from prompts + rosters via scripts/generate-templates.py (read). Never hand-edit.

One bot cited by path: grokbot/templates/LEAD.md (LEAD seat; also prompts/bot-00-programming-lead.xml as source).

## 6. Publish mechanism

**Sourced (not UNKNOWN).**

Mechanism (from re-ran greps on "swcstudiospace", "Add Bot", "publish", "deploy", "Share", "template"; reads of upgrade-plan §9, grokbot/README.md, scripts/, docs/):

1. **Generate** (in repo):
   - `bash scripts/assemble-prompts.sh [--roster grokbot/rosters/<team>.json] [--check]`
     - Prepends core, substitutes placeholders from roster, writes prompts-assembled/ + aliases.
   - `python3 scripts/generate-templates.py [--roster ...] [--check]`
     - Reads prompts + contracts/tool-rosters/, renders grokbot/templates/<SEAT>.md (strips secrets/UUIDs/tailnets per G-7/FORBIDDEN).
   - `python3 ci/gates/check_desk_integrity.py` (G-7).

2. **Grok Bot UI publish**:
   - For each seat: Share → Create template → **Team-only**.
   - Copies: name, description (charter + "First run: /desk bootstrap" + gateway), enabled skills, routines (paused), avatar.
   - Does **not** copy: UUIDs, channel id, prompt body, tokens, memory, history, credentials, computer, group.
   - Ids not secrets (rosters/<team>.json committed for spectrumwebco; recipient teams use desk_doctor register).

3. **Install on recipient team** (from template):
   - Add 7 templates.
   - Each: `/desk bootstrap` (skills/desk-bootstrap/SKILL.md):
     - Add MCP Server → `desk-<seat>` at `https://desk.swcstudio.space/mcp/<seat>` (OAuth, passphrase).
     - `desk_doctor register` (agent_uuid from /home/box/agent-data/agents/<uuid>/ ; LEAD adds channel_id).
     - Wait for roster 7 + channel.
     - `desk_doctor install_prompt` → write SYSTEM_PROMPT.xml → report sha.
     - `desk_doctor check` (prompt hash match, skills in / list, etc.).
   - LEAD un-pauses routines only when all green.
   - Fresh-desk acceptance: new team adds templates, runs bootstrap, full e2e with receipts (see upgrade-plan §9.4, intake-e2e-runbook.md).

4. **Roster**:
   - `grokbot/rosters/<team>.json` (for assemble outside gateway): team, roster_version, desk_channel_id, gateway_url, seats UUIDs.
   - Live: via gateway `desk_doctor register` + `desk_roster_status`.
   - Example: grokbot/rosters/spectrumwebco.json (read).

5. **Other**:
   - Gateway deploy: INFRA (infra/desk-gateway/, services/desk-gateway/).
   - Skills packaging: to Marketplace `swc-programming-desk` plugin (future); shared via agent-skills projector.
   - GitHub: swcstudiospace/programming-desk (transferred); receipts cite PRs.
   - No direct "publish" in code beyond scripts + manual Grok "Share"; "deploy" mostly for infra (Vercel/Railway/Play via tools, G-5).

Evidence paths:
- docs/upgrade-plan-desk-v2.md §9 "Grok Bot share: install the desk from Add Bot", §8 (read full sections).
- grokbot/README.md (read).
- scripts/generate-templates.py (full read), scripts/assemble-prompts.sh (read).
- grokbot/templates/*.md headers.
- .receipts/.../desk-v2-*.json (e.g. bot-00.../desk-v2-grokbot-share.json).
- contracts/tool-rosters/, prompts/.
- Grep hits: "Share -> Create template", "Add MCP Server", "desk.swcstudio.space", "swcstudiospace/programming-desk".

**Verification per spec:**
- One bot cited by path: `grokbot/templates/LEAD.md` (and source `prompts/bot-00-programming-lead.xml`).
- Publish: sourced (detailed above from upgrade-plan + scripts + templates; not UNKNOWN).

## Additional notes from reads/greps
- 7 seats + QUALITY off-channel.
- G-1..G-6 + G-7 (desk integrity) executable in ci/gates/.
- Receipts in .receipts/<bot-id>/ (per-bot owned).
- All steps re-ran with bash/read/grep on 2026-09-30.
- No CLAUDE/AGENTS.md at root (AGENTS.md in sibling repos); docs/ + READMEs read first.

**End of n3 audit inventory.**
