# Phase 1: Inventory and prove assumptions — Pattern Map

**Mapped:** 2026-10-08  
**Files analyzed:** 10 candidate artifact/source path families. `NN` and `<task-id>` denote existing naming conventions, not assigned plan numbers or invented task identities.  
**Analogs found:** 6 / 10 have close tracked repository analogs: 5 exact role/data-flow matches and 1 role match. Four GSD artifact families lack close tracked repository precedents.  
**Status:** Pattern mapping complete; Phase 1 remains incomplete/unverified. No downstream dependency is cleared.

## Scope and Evidence Rules

Inputs: [CONTEXT](01-CONTEXT.md), [RESEARCH](01-RESEARCH.md), [inventory Markdown](01-INVENTORY.md), [inventory JSON](01-INVENTORY.json), [implementation map](../../intel/implementation-map.md), and the parent's newly seeded [validation strategy](01-VALIDATION.md). Canonical scope remains [PROJECT](../../PROJECT.md), [requirements](../../REQUIREMENTS.md), [ROADMAP](../../ROADMAP.md), [resolved decisions](../../INGEST-CONFLICTS.md) and [constraints](../../intel/constraints.md).

- Cover **REQ-INVENTORY-001 through REQ-INVENTORY-016**: kickoff, all six n1 steps and prerequisite inventory. Preserve the full seven-node/41-step tracker graph. Tracking later nodes does not dispatch or deliver them.
- Phase 1 updates evidence/assumptions, not gateways, forwarders, ACLs, data adapters/migrations, skills, templates, plugins or release integrations. The documented gateway-skeleton overlap starts only **after verified n1**, not during this mapping.
- `.planning/**` and LEAD's own receipts are LEAD-owned. Proposal §13 and QUALITY's own receipts are separate QUALITY-owned deliveries. The mapper writes only this file.
- Source declarations, versioned schemas, historical receipts, configured services, container listeners, public health, fixtures and actual authenticated client results are distinct evidence classes. Never promote one into another.
- Named repository analogs/supporting excerpts were identified in the git index with `git ls-files -- <path>`. Fresh planning inputs, including `01-VALIDATION.md`, were not returned; they are current inputs/targets, **not claimed as tracked analogs**. Installed/runtime mirrors are not implementation targets.
- Root `CLAUDE.md` and configured `.claude/CLAUDE.md` were not found. `.claude/skills/desk-swarm/` contains `generate.py` and `roster.json`, but no `SKILL.md` index was found; `.agents/skills/` was absent. No additional project skill rules were inferred.

## File Classification

`P` means `.planning/phases/01-inventory-and-prove-assumptions/`. Match quality describes structure/responsibility, **never acceptance**.

| New/Modified File | Responsibility / timing | Role | Data Flow | Closest Tracked Analog | Match Quality |
|---|---|---|---|---|---|
| `P/01-NN-PLAN.md` | Independent planner; LEAD planning, before execution | config | transform; request-response checkpoints | No close GSD plan; ticket support in `docs/desk-operating-model.md:153-178` | none — format gap |
| `P/01-VALIDATION.md` | Parent-seeded draft; planner binds actual tasks | test | batch; request-response/manual evidence | No close GSD validation document; coverage support in `ci/tests/test_gates.py:244-336` | none — format gap |
| `P/01-INVENTORY.md` | Existing LEAD human-readable evidence | utility | request-response → transform | `docs/upgrade-plan-desk-v2.md:334-349` | exact |
| `P/01-INVENTORY.json` | Existing LEAD machine snapshot; retain its schema/provenance | model | request-response → file-I/O | `.receipts/bot-00-programming-lead/desk-swarm-subagents.json:6-78` | role-match — evidence model, not inventory schema |
| `.planning/intel/implementation-map.md` | Existing LEAD seven-phase source/evidence reconciliation | utility | batch → transform | `docs/upgrade-plan-desk-v2.md:294-308` | exact |
| `docs/upgrade-plan-desk-v2.md` **§13 only** | QUALITY n1.6 update through actual owned ticket/delivery | utility | transform | Same tracked file, `:334-349` | exact |
| `.receipts/bot-00-programming-lead/<task-id>.json` | Actual LEAD orchestration/integration; Main owns checks | model | event-driven; file-I/O | `.receipts/bot-00-programming-lead/desk-swarm-subagents.json` | exact |
| `.receipts/bot-06-quality-security/<task-id>.json` | Actual QUALITY §13 delivery; independent reviewer | model | event-driven; file-I/O | `.receipts/bot-06-quality-security/desk-v2-upgrade-plan.json` | exact |
| `P/01-NN-SUMMARY.md` | Lifecycle target **only after actual plan completion** | utility | batch → transform | No close tracked GSD summary | none |
| `P/01-VERIFICATION.md` | Lifecycle target for actual phase verification; parent progression | test | batch; request-response/manual evidence | No close tracked GSD verification report | none |

The last two families describe the installed GSD lifecycle, not authorization to write summaries, approve the phase or choose plan/task bindings now. Packet/attachment persistence filenames are unspecified; record actual references in existing inventory/receipts rather than inventing `UPLIFT.xml`, a new evidence directory or a second tracker store.

### Unchanged Inputs and Read-Only/Downstream Source Paths

These referenced paths are **not Phase 1 product-edit candidates**. Family notation classifies them without adding them to `files_modified`.

| Path(s) | Role / Data Flow | Phase 1 use and ownership boundary |
|---|---|---|
| `01-CONTEXT.md`, `01-RESEARCH.md`, `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/INGEST-CONFLICTS.md`, `.planning/intel/constraints.md` | config/utility; transform | Canonical scope/evidence rules. Parent's reported downstream schema/polling corrections change no Phase 1 decision. |
| `.planning/STATE.md`, `.planning/ROADMAP.md`, `.planning/config.json` | store/config; transform | Parent-owned registered progression/config. PATTERNS existence never advances them. |
| `skills/gotxcot-uplift/SKILL.md`, `skills/trackplan-dispatch/SKILL.md`, `vendor/ultrathink-policy/kickoff-checklist.md` | utility/config; transform, CRUD, event-driven | Existing LEAD packet/materialization/dispatch procedures; no edit or claimed dispatch. |
| `ownership.yaml`, `docs/cross-bot-protocol.md`, `docs/handoff-contracts.md`, `skills/verification-receipts/SKILL.md`, `docs/quality-gates.md`, `SECURITY.md` | config/model/utility; transform, event-driven | Existing governance with explicit owners. Definitions are not signatures, approvals or consumer acknowledgements. |
| `ci/gates/{check_ownership,check_receipt,check_secrets,check_contracts,check_rollback,check_desk_integrity,run_all}.py`; `ci/tests/test_gates.py` | utility/test; batch, file-I/O | QUALITY gate infrastructure; Main's later checks only. No new framework/bypass. |
| `.github/workflows/gates.yml`, `.github/workflows/desk-intake.yml`, `ci/.github/workflows/gates.yml` | config; event-driven, batch | Root declaration versus actual remote run/runner. General root workflows are INFRA; later `ci/.github/**` makes nested template QUALITY. |
| `services/desk-gateway/src/desk_gateway/{server,config,rosters,schema,store,oauth,upstreams}.py`, `tools/{core,packs,quality,lead,mobile}.py`; `services/desk-gateway/pyproject.toml` | route/middleware/service/model/config; request-response, CRUD, transform | SYSTEMS source references only. Rendering, supplied hashes, discovery and approval commits do not prove actual client acceptance. |
| `infra/railway/**`, `infra/tailscale/**`, `infra/desk-gateway/**`, `infra/substrate/SUBSTRATE-ENV.md` | config/utility; transform, file-I/O | INFRA network/custody specifications. No applying mappings, service restart, secret dump or exposure retirement in n1. |
| `grokbot/rosters/spectrumwebco.json`, `grokbot/templates/**`, `grokbot/avatars/**`, `contracts/tool-rosters/**`, `contracts/tool-packs/**` | model/config; transform | Source definitions, not self-UUID/connector/publication proof. LEAD owns grokbot; QUALITY owns contracts with consumers. |
| `prompts/**`, `prompts-assembled/**`, `scripts/assemble-prompts.sh`, `scripts/generate-templates.py`, `skills/tool-packs/SKILL.md` and §8.2 skill sources | config/utility; transform, file-I/O | Later n5 owned work. No assembly/activation/publication during mapping. |
| Referenced `agent-substrate` docs/env/README/PROJECT, `packages/mcp-server/src/{planes,service,index-store}.ts`, `packages/ledger/**`, projector sources | service/model/config; CRUD, streaming/event-driven, transform | Companion-owner later work. No companion inspection/edit here; reports lack exact map-time revision and later dirty HEAD does not supply it. |
| Actual participating Bot's own `SYSTEM_PROMPT.xml` | config; file-I/O | External runtime subject, **not a repository file or invented UUID path**. Actual Bot/human must establish identity, private original bytes, write and readback. |

## Pattern Assignments

### 1. `01-NN-PLAN.md` — GSD Format, Owned-Ticket Semantics

**Close tracked format analog:** None. The loaded installed GSD `phase-prompt.md` supplies format; tracked tickets supply responsibility/reporting semantics, not a replacement plan schema.

**Tracked support:** [Operating-model ticket](../../../docs/desk-operating-model.md#ticket-format), lines 153-178. Keep `task_id`, `owner`, `goal`, `paths_in_scope`, `out_of_scope`, `trackers`, `success_criteria`, `report_back`. Concrete excerpt, lines 168-178:

```markdown
- **trackers:** (when a graph exists) Graph ID, Notion Issue/Sub-Issue URLs, Linear issue/sub-issue URLs from the second uplift. Do not paste the entire XML into chat if the packet already lives on the branch; cite it.
- **success_criteria:**
  - Unit tests for token registration pass (`./gradlew :app:testDebugUnitTest`)
  - Receipt at `.receipts/bot-03-android/<task_id>.json` with cited commands and the brief record (`brief_etag`, or `brief_read_at` + `cached`)
  - No owned-path violations (G-1)
  - Production loop run: brief before the first edit with a revision marker or a recorded degraded-mode ack, `memory_write` and `events_emit` in the same turn, per-plane retain outcome recorded
- **report_back:**
  - Receipt path
  - Summary of files changed
  - `unverified` list (devices / OS versions not exercised)
  - Blockers for LEAD (if any)
```

Copy field/reporting shape, **not Android tests/identities/claims**. Inventory plans use actual n1 requirements, owners and evidence.

**Existing GSD format:** phase/plan/type/wave/depends_on/files_modified/autonomous/requirements/must_haves frontmatter; task files/read_first/action/verify/acceptance/completion conditions. Mapper assigns no plan count or task identity. Genuine human-checkpoint plans are not autonomous. Keep seeded validation's adjacent `<automated>`/`<fails_when>` requirements; string assertions cannot certify live subjects.

**Human guard:** Loaded checkpoint guidance explicitly distinguishes `gate="blocking"` from **`gate="blocking-human"`**, which never auto-approves in any mode. Use `checkpoint:human-action` for genuinely human-only computer/account/approval actions and the non-bypassable gate for trust-establishing/manual evidence stops. A resume message alone is not UUID/write/readback/client/account/review evidence. Do not copy generic requests to paste secrets: phase privacy rules prohibit them.

**Imports:** Not applicable. Do not create application code to make manual acceptance look automated.

### 2. `01-VALIDATION.md` — Bind the Parent's Draft

**Current target/convention seed:** [Actual validation strategy](01-VALIDATION.md), lines 1-8:

```yaml
---
phase: "01"
slug: "inventory-and-prove-assumptions"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-08"
---
```

It covers all 16 requirements, manual/live boundaries and pending sign-off without predetermined PLAN bindings. Provenance lookup returned no tracked path: extend it **in place as current input**, not a claimed historical analog. Bind actual tasks/threats after independent planning; planning alone changes no sign-off boolean.

**Close tracked format analog:** None. Loaded installed `VALIDATION.md` defines draft frontmatter, infrastructure/sampling, task verification map, manual-only rows and sign-off. Its tracked origin was not established; no installation path is a repository edit target.

**Existing testing support:** [Gate tests](../../../ci/tests/test_gates.py), imports/helper lines 24-37:

```python
from pathlib import Path

import pytest

GATES = Path(__file__).resolve().parents[1] / "gates"
REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "ownership.yaml"


def run_gate(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATES / script), *args],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
```

**Rejection pattern**, lines 316-321:

```python
    def test_no_commands_blocked(self, tmp_path):
        """Nothing was run, so nothing is verified."""
        p = write_receipt(tmp_path, commands=[], claims=[])
        r = run_gate("check_receipt.py", "--receipt", str(p))
        assert r.returncode == 1
        assert "no commands recorded" in r.stderr
```

Opened `TestG1Ownership`/`TestG2Receipts` also exercise foreign/unowned paths and failed/missing evidence. These prove **gate behavior if actually run**, not account/client/service acceptance. Use seeded quick/full commands for Main's later consolidated checks; no mock Bot tests, new framework/install or production smoke task is justified in n1.

### 3. `01-INVENTORY.md` — Subject/Status/Resolution

**Analog:** [Proposal §13](../../../docs/upgrade-plan-desk-v2.md#13-assumptions-ambiguities-and-what-was-not-verified), lines 334-349. Same role/data flow: facts transformed into an assumption/status record.

**Concrete fragment**, lines 336-340:

```markdown
| Item | Status | Resolves in |
|---|---|---|
| Railway service names (`greptimedb`, `timescaledb`, `dragonfly`, `hindsight-api`, `ragflow`) and ports (Greptime 4000/4001/4003, Timescale 5432, Dragonfly 6379, Hindsight 8888, RAGFlow 9380/80) | Assumed from defaults and the substrate env; the projects are not visible from this session's Railway connection | n1 |
| Bot can read its UUID and write `SYSTEM_PROMPT.xml` under `/home/box/agent-data/agents/<uuid>/` | Path stated in `ARCHITECTURE.md`; write access not proven | n1 |
| Grok Bot MCP client honours `tools/list_changed` | Unverified; fallback endpoints designed | n1 |
```

Copy table shape, **not stale proposal assertions**. Existing inventory adds observer attribution, actual identifiers/commands/results, failed attempts and omissions. Preserve it and add only genuine evidence.

Distinguish configuration/listener, container/private DNS/traversal, public health/authentication, actual self-identity/roster value, attempted account access/effective policy. Preserve missing historical timestamps. DNS/relay/`ss` failures remain bounded failures; curl exit 0 does not make HTTP 503 healthy. Extra listeners 4002/9382 do not expand authorized mappings.

### 4. `01-INVENTORY.json` — Keep Schema 1 and Provenance

**Closest tracked analog:** [LEAD receipt](../../../.receipts/bot-00-programming-lead/desk-swarm-subagents.json), lines 6-78. Same JSON evidence-model role; **different schema**.

**Historical evidence separation**, lines 74-76:

```json
    "These are adapted, not ported. The upstream agent-swarm bodies carry long role/domain/stack sections and a detailed per-agent procedure; this generator keeps the description, capabilities, lane, caps and tools, and replaces the rest with desk governance. A generated agent therefore knows less about its craft than its omp original. That was deliberate — the upstream bodies reference a runtime this repo does not have (scripts/orch_plan.py, a .swarm/ task store, a yield tool) — but it is a real loss of depth, and the place to recover it is roster.json rather than the generated files.",
    "roster.json is a point-in-time copy of agent-swarm's agents.json (swarm.manifest.v1 1.0.0) and will drift from it. Nothing syncs them and nothing detects divergence. The copy is deliberate so a bare clone of this repository is self-contained, but an upstream roster change will not arrive here on its own.",
    "generate.py --check does not run in CI. The gates workflow collects ci/tests/, so a roster edit committed without regenerating produces a stale tree that no gate catches. Wiring --check into the workflow is an INFRA change to .github/workflows/, not this seat's path.",
```

This excerpt illustrates explicit source/runtime/owner limits; it is **not a new finding about current dispatch or CI**. Copy the discipline, never old results.

**Current schema authority:** `01-INVENTORY.json:2-21` contains `schema_version: 1`, `status: incomplete_unverified`, baseline and `runtime_observer: parent`. Preserve `durable_references`, `parent_command_supplement`, `runtime_evidence`, complete `source_analyses`, `pending_phase_1`, `resolved_policy`, `checks_executed_by_worker`, `companion_checkout_provenance`. Do not replace these with receipt fields or silently bump schema.

Capture actual subject/observer/action/result/time when available/durable reference/limitation. UI evidence stays actual sanitized screenshots/transcripts, not synthetic commands/exits. Six stored SSH invocations remain **parent observations**, not worker re-execution.

### 5. `.planning/intel/implementation-map.md` — Owners, Capabilities, Gaps

**Analog:** [Proposal §11](../../../docs/upgrade-plan-desk-v2.md#11-repository-changes-in-this-repo), lines 294-308. Concrete excerpt, lines 296-298:

```markdown
| Change | Owner | Notes |
|---|---|---|
| `docs/upgrade-plan-desk-v2.md` (this file) | QUALITY (`docs/**`) | Plan of record until superseded |
```

Keep explicit ownership alongside the current map's phase/source-step, authored capability/exact source and remaining delivery/evidence. Authored capability is not deployment. Preserve all seven phases and later gates.

Companion reports are bounded source analyses, not exact current snapshots. Later dirty HEAD is not map-time revision. No certifying applicability, merging/resetting/editing companion user work or reusing prior completion labels as Desk acceptance.

### 6. Proposal §13 — Separate QUALITY-Owned Delivery

**Analog:** The same tracked §13 table in assignment 3. Preserve all subjects, §1 ORIGINAL, complete source scope, D-1/D-2/D-3 and D-4's original-authoring-session history.

**Ticket pattern:** `docs/desk-operating-model.md:138-151,153-178`: concrete owning-seat ticket, actual second-uplift tracker links, owned work, `awaiting-review / pending QUALITY` result. LEAD routes actual n1.6 evidence/ticket; QUALITY edits §13 and authors its own receipt. No fabricated ticket/dispatch/signature.

Required dispositions:

1. Correct old Railway invisibility/default-only statements using parent project/environment/service/listener records; retain authorization/private-DNS/traversal/unobserved-environment limits.
2. Correct railway-app's unknown project with hostname proof; preserve bounded subnet-advertiser role and later suitability/retirement gates.
3. Correct root-workflow absence from opened root source; remote activation/runner/current-SHA successful run remains unverified without actual evidence.
4. Add actual Bot UUID/path/write-readback, client notification/fallback, Cursor tier/effective policy/triggers **only when obtained**. Hints/fixtures/access failures remain bounded.
5. Record mobile availability/custody without values; distinguish configured Hindsight image from actual API version/provider/model/dimensions. Image/health supplies neither compatibility nor first-write clearance.
6. Retain Bot-created-Bot non-reliance, ten-minute intake-poll floor, original-session provenance and unverified E2E. Later skill installation/publication stays an authorized human account action.

**Integration guard:** Opened workflow attributes one bot from branch prefix; opened G-1 flags a non-contract QUALITY document in a LEAD diff as foreign. Separate receipts create no multi-owner exemption. Keep the fixed LEAD branch. Parent must establish actual owner-attributed QUALITY delivery/integration/base or stop at an integration checkpoint. No ownership rewrite, foreign LEAD edit, branch switch or imaginary merge.

### 7. LEAD Receipt — Actual Orchestration Evidence

**Analog:** `.receipts/bot-00-programming-lead/desk-swarm-subagents.json:6-69,70-78,80-91`: recorded command/indexed claim/specific limit/changed-file separation.

**Dispatch support:** [Work packet](../../../skills/trackplan-dispatch/SKILL.md#github-sot-work-packet), lines 84-105: repo/graph/branch/ref, real Linear/Notion URLs, runtime/owner, scope/acceptance, receipt/report-back. Concrete idempotency excerpt, lines 195-204:

```markdown
Do **not** double-launch the same `graphId` + node subset without an explicit operator request.

Before launch:

1. Look for a running Cloud Agent whose title or prompt cites this `graphId` or primary Linear id. If you cannot list agents, write `unverified` — do not assume none exist.
2. Search open GitHub PRs for the `graph_id` or Linear ids.
3. If the Notion Task already has a `PR URL` or a recorded agent id, confirm with the operator before a second launch.
4. Re-entrant kickoff may update tracker rows. Dispatch is not automatically re-entrant.
```

Keep actual fixed branch/task identity; record only performed orchestration/returned URLs/genuine dispatch. Dispatch only n1; later rows supply no execution clearance. The skill's exit-0 sample is schema illustration, not permission to assign shell exits to UI actions, STOP or uncalled APIs.

**Signature limit:** Worker dispatch is authenticated omp, not a supplied signed AgentSwarm assignment. No bus signature was supplied. Never invent signatures, acknowledgements, Cloud Agent/job IDs or claim the source-described API was called.

### 8. QUALITY Receipt — Actual Author, Independent Reviewer

**Analog:** [Historical proposal receipt](../../../.receipts/bot-06-quality-security/desk-v2-upgrade-plan.json), lines 6-59,60-64. Concrete limits:

```json
  "unverified": [
    "Greptile review of PR #16 may still be in progress at receipt write time",
    "Downstream stack PRs #17\u2013#24 not merged; plan correctness for live seats unproven",
    "Railway/Tailscale operational cutover not exercised by this docs-only PR"
  ],
```

Historical references, approval value, dates/notes/checks are **not this phase's evidence or approval**. Some recorded commands are abbreviated and some claims exceed manifest self-check coverage; do not replay/inherit them. Use current skill/checker.

`docs/quality-gates.md:278-295` forbids QUALITY self-approval: its document receipt needs actual LEAD/human independent review. LEAD consolidation still requires requested QUALITY review. Gate/hook changes require a human, but no gate change belongs to n1.

### 9. `01-NN-SUMMARY.md` — Only After Real Completion

**Close tracked GSD analog:** None. Use installed summary convention after the corresponding plan actually completes. Derive files/behavior/decisions/evidence from actual results. Tracked reporting guard: `docs/desk-operating-model.md:198-201`, LEAD never fabricates specialist receipts and requires consolidation/requested QUALITY approval.

A blocked checkpoint remains resumable, not completed. No fictional duration/commit/approval/pass/downstream clearance.

### 10. `01-VERIFICATION.md` — Goal Evidence, Not Presence

**Close tracked GSD analog:** None. Loaded verification-report format distinguishes `passed`, `gaps_found`, `human_needed`, behavior-unverified truths, requirements and manual evidence. Its fingerprint prefix `v1:sha256:` is **format**, not a computed digest or verified subject.

Use actual Main/verifier outputs for all 16 requirements/must-haves. Gate tests never close manual/live rows. Preserve missing-human/behavior evidence. Parent owns progression; PATTERNS/draft validation/file presence never sets Phase 1 passed.

## Shared Patterns

### A. Full Double-Uplift and Tracker Hierarchy

**Apply to:** Plans, packet/inventory references, LEAD receipt and actual external tracking actions.

[Uplift skill](../../../skills/gotxcot-uplift/SKILL.md), lines 48-62, requires one approved XML root, first/last characters `<`/`>`, filled `ORIGINAL`, `SYSTEM_ROLE`, `CONTEXT` or `APP_CONTEXT`, `SCOPE`, `CONSTRAINTS`, `ACCEPTANCE_CRITERIA`, `OUT_OF_SCOPE`. Concrete requirements, lines 54-62:

```markdown
- `ORIGINAL` — operator text **verbatim**. Not a paraphrase. Not prior conversation.
- `SYSTEM_ROLE`
- `CONTEXT` or `APP_CONTEXT`
- `SCOPE`
- `CONSTRAINTS` — always include “do not invent repository facts”
- `ACCEPTANCE_CRITERIA` — observable
- `OUT_OF_SCOPE`

Add when relevant, and do not add empty stubs: `PLATFORM_CONSTRAINTS`, `DESIGN_SYSTEM_CONTINUITY`, `SECURITY_AND_VALIDATION`, `GRACEFUL_DEGRADATION`, `STATES`, `WORKFLOW`, `ASSUMPTIONS`, `AMBIGUITIES`, plus **named nested sections** for the surfaces in the ask (pages, modals, APIs, jobs). Domain-shaped tags, not `<item>` soup.
```

Copy **complete** operator block from `docs/upgrade-plan-desk-v2.md:15`, not a shortened research quote. Second uplift extends full first XML and nests `ISSUES`/`CLARIFICATIONS` inside root (`:163-194`). Placeholder URLs/shortened packets/Markdown tables do not substitute.

[Kickoff checklist](../../../vendor/ultrathink-policy/kickoff-checklist.md), line 37:

> Query `Graph ID` = `plan.graphId`. Re-entrant kickoff **updates**; it does not duplicate the Task.

Lines 54-68 specify an Issue per node and Sub-Issue per step in both trackers; step `Parent Item` is its node Issue. Source-configured destination/team are not actual graph identity/write authority. Locked totals: **49 Notion rows** (Task + 7 + 41), **48 Linear issues** (7 + 41), derived requirements **not created totals**.

Fetch actual schema/parents/children, retain real URLs/failure pairs, confirm complete readback during execution. Parent-reported destination/team discovery establishes no graph key, write permission/quota or complete rows. Stop/resume full graph on quota/access failure; approved scope does not select generic compact/tracker-less/default-on-human-absence alternatives.

### B. Ordered Ownership and Contract Consumers

**Apply to:** Every planned path/owning slice. [Manifest](../../../ownership.yaml) excerpts: lines 223-224,235-240,401-402.

```yaml
  - pattern: ".receipts/bot-00-programming-lead/**"
    owner: bot-00-programming-lead
```

```yaml
  - pattern: ".receipts/bot-06-quality-security/**"
    owner: bot-06-quality-security

  # --- Docs --------------------------------------------------------------
  - pattern: "docs/**"
    owner: bot-06-quality-security
```

```yaml
  - pattern: ".planning/**"
    owner: bot-00-programming-lead
```

[Executable resolver](../../../ci/gates/check_ownership.py), lines 62-72:

```python
def resolve_owner(path: str, manifest: dict) -> tuple[str | None, bool]:
    """Return (owner, is_contract_surface). Last matching rule wins."""
    owner: str | None = None
    contract = False
    for rule in manifest.get("ownership", []):
        for pattern in [p.strip() for p in rule["pattern"].split(",")]:
            if _match(pattern, path):
                owner = rule["owner"]
                contract = bool(rule.get("contract_surface"))
                break
    return owner, contract
```

Lines 143-163 fail unowned/foreign paths. No default owner, first-match reading or general mixed-owner exemption. Preserve later language/directory overrides, final `**/*.proto` contract rule and nested-template QUALITY override.

`ownership.yaml:355-360,436-447` declares roster/pack contract surfaces: roster consumers all seven seats; pack consumers WEB/ANDROID/IOS. Lists are not acknowledgements. Real contract-first work remains later; n1 prose reconciliation needs no invented API contract.

### C. Receipt Validation and Honest Errors

**Apply to:** Both receipt owners; inventory borrows discipline, not schema.

[Receipt checker](../../../ci/gates/check_receipt.py), imports `:15-21`: stdlib `argparse`, `json`, `re`, `sys`, `Path`. `:377-385` maps missing files/invalid JSON to `ReceiptError`; reuse it, no parallel validator.

**Required fields**, lines 48,55-56:

```python
REQUIRED_FIELDS = ["task_id", "bot", "commands", "claims", "unverified"]
```

```python
REQUIRED_LOOP_ACK_FIELDS = ["condition", "operation", "ack_id", "human_granted_by", "at", "scope"]
LOOP_ACK_CONDITIONS = {"brief_degraded", "brief_no_revision_marker"}
```

**Fail-closed evidence/review**, lines 403-410,416-423:

```python
    if not isinstance(commands, list) or not commands:
        problems.append(
            "no commands recorded — nothing was actually run, so nothing is verified"
        )
    if not isinstance(claims, list):
        problems.append("'claims' must be a list")
    if not isinstance(unverified, list):
        problems.append("'unverified' must be a list (an empty list is allowed but rarely honest)")
```

```python
    approved_by = receipt.get("approved_by")
    if not approved_by:
        problems.append("'approved_by' is missing — work must be reviewed by someone else")
    elif approved_by == receipt.get("bot"):
        problems.append(
            f"self-approval: approved_by == bot ({approved_by}). "
            "A bot approving its own work removes the independent check."
        )
```

[Receipt skill](../../../skills/verification-receipts/SKILL.md), `:60-113,207-240`: actual `commands[].cmd/exit_code/duration_s/output_tail`, indexed claims, `expects_failure`, specific `unverified`. `expects_failure` describes real expected failure, not an excuse for failed success evidence. No copied results or synthetic UI exits.

`loop_acks` is genuine human permission for a named degraded **turn**, separate from destructive/deploy `approvals[]`. No supplied dispatch/schema/healthy-looking object manufactures acknowledgement. Parent's unhealthy brief remains an actual specialist-execution prerequisite under the operating model.

### D. Actual Client Auth/Discovery, Not a New Server

**Apply to:** n1.3/n1.4 evidence acquisition only.

[Server auth/discovery](../../../services/desk-gateway/src/desk_gateway/server.py), lines 81-88:

```python
    def _surface(self) -> tuple[str, dict[str, ToolSpec]]:
        seat = current_seat.get() or seat_of(get_access_token())
        if seat is None or seat not in SEATS:
            raise PermissionError("no seat")
        pack = current_pack.get()
        if pack:
            return seat, self.services.rosters.pack_surface(seat, pack)
        return seat, self.services.rosters.surface(seat, self.services.store.packs_for(seat))
```

`server.py:46` declares same-seat `/mcp/<seat>/packs/<pack>` routing; `:186-191` rejects wrong-seat tokens/unknown packs. Source guards are not authorized SaaS connection proof.

[Existing fallback response](../../../services/desk-gateway/src/desk_gateway/tools/packs.py), lines 32-39:

```python
    records = svc.store.load_pack(ctx.short, app, args["task_id"])
    return {
        "ok": True,
        "loaded": records,
        "tools": sorted(pack.tools),
        "live_tools": len(svc.rosters.surface(ctx.short, [r["app"] for r in records])),
        "note": "the pack's tools appear on the next tools/list; if Grok Bot does not refresh, enable the pack connector at /mcp/<seat>/packs/<app>",
    }
```

Opened load body updates state/returns next-list note without a notification-send call. Establish emission/delivery first; that observation does **not** prove SDK/client non-support. Capture actual protocol/transport/delivery/client rediscovery. RESEARCH distinguishes MCP **2025-11-25** and **2026-07-28** notification/subscription rules; do not assume newest negotiation or upgrade inventory deployment. Exercise authorized fallback only on observed client non-support; unavailable server/access is not unsupported client.

**Anti-analog:** `tools/core.py:203-225,231-240` consumes supplied UUID, returns `install_path_hint`, compares supplied prompt hash/installed skills. It does not read/write actual remote Bot file. Actual self-namespace and private preserved-byte write/readback remain human/Bot evidence; no registration/bootstrap/fixture substitute.

### E. Exact-SHA Review: Specified, Not Proved Available

**Apply to:** QUALITY §13 result, LEAD consolidation, verification/merge claims.

[Operating model](../../../docs/desk-operating-model.md#merge-claim-head-rule), line 209:

> An approval must be bound to a sha, and must not create one.

Lines 226-233 specify `approval_ref.kind` (`check_run`, `pr_review`, `gateway_store`), `name`, actual `reviewed_sha`, resolved against exact current head. This is **specified contract**, not a proved resolver/check-run permission/approval.

Opened checker still requires non-self `approved_by`; this map establishes no working `approval_ref` resolver. Opened `tools/quality.py:174-189` calls `_commit_file`; `:341-351` commits/pushes the approval. Candidate gating/tip-race protection do not review the new tip. **Do not copy approval-as-commit.** Historical stamps supply no current-SHA clearance.

Parent must obtain actual independent exact-final-SHA review through available non-commit route and confirm real gate consumption. If unavailable, keep progression/merge/review blocked and route owning prerequisite. Implementing gateway/gate resolver remains downstream delivery, not n1 workaround.

### F. Versioned Security/Evidence and Redaction

**Apply to:** Every plan/manual attachment/inventory/receipt.

- Inventory `schema_version: 1`, baseline and observer are existing evidence convention, not runtime validation.
- Manifest `version: 1` plus executable last-match resolution is existing ownership convention.
- [Handoff contract](../../../docs/handoff-contracts.md), `:12-27`, specifies `envelope_version: "1.0"`, actor/subject/time/causal IDs, receipt, human-gate flag and fact-derived idempotency. Typed examples are not dispatched/signed messages. Populate only actual facts if channel genuinely used; no synthetic envelope/signature for omp.
- Opened config requires Nyquist, ASVS L1/high-severity blocking and real checkpoints. Keep required PLAN threat models and validation threat/secure-behavior references; no speculative threat closure/audit sign-off.
- RESEARCH `:658-681` supplies explicitly versioned **ASVS 5.0.0**: V6 authentication, V7 sessions, V8 authorization, V2 validation/business logic, V11 cryptography, V14 protection, V16 logging/errors, V10 OAuth/OIDC where applicable. Do not relabel older chapter numbering or invent control IDs. Mapper did not re-fetch OWASP/exercise controls; these are research references and planned obligations.
- Installed GSD's `v1:sha256:` fingerprints/behavior-unverified fields are formatting conventions, not computed digest/pass/certification/score.

[SECURITY.md](../../../SECURITY.md#3-no-secrets-in-receipts), lines 95-105, concrete excerpt:

```markdown
- **Redact, do not delete.** `Authorization: Bearer <redacted>` keeps the command re-runnable in
  shape and reviewable in intent. Silently dropping the flag makes the transcript a lie.
- **Reference the secret, never the value.** Name the variable or the secret-manager path
  (`$DEPLOY_TOKEN`, `vault:kv/ci/deploy`), not the material.
- **Truncate output to the tail you actually need.** `output_tail` exists to carry the result
  line, not the whole log. A full log is where a credential hides.
- **Use a non-production credential for verification** wherever the check allows it. A receipt
  recording a run against a scratch environment carries a far smaller blast radius when it does
  leak something.
- **Redaction is not a silencer.** If the run genuinely could not be verified without a
  production credential, that belongs in `unverified[]`, stated plainly.
```

Only credential availability/owner/scope metadata; never tokens/cookies/keys/full prompt bytes/env dumps. `infra/substrate/SUBSTRATE-ENV.md:25-39` documents private substrate data credentials/private gateway platform credentials, not actual runtime presence/permissions. Do not use mobile status/release calls as presence probes; RESEARCH identifies Play edit side effect.

### G. Root CI and Trusted-Base Execution

**Apply to:** REQ-INVENTORY-014, integration and Main's later verification.

[Root workflow](../../../.github/workflows/gates.yml), lines 55-59:

```yaml
          BASE_REF: ${{ github.base_ref || 'main' }}
        run: |
          set -euo pipefail
          git fetch --no-tags --depth=1 origin "$BASE_REF"
          git checkout "origin/$BASE_REF" -- ci/gates/
```

Preserve trusted-base overlay/env-based ref handling. PR-controlled gate code is data, not trusted executable code. `:70-99` attributes one bot/runs G-1; `:108-153` selects this change's receipt, disambiguating by branch instead of arbitrary historical receipt. New receipts name actual branch for that reason.

Root source/self-hosted runner/Python/test/scanner declarations prove no remote registration, runner availability, completed run, green gates or permissions. Main obtains actual applicable event/branch/SHA/run evidence for activation. No installing/dispatching/rerunning CI in mapping.

## Requirement-to-Pattern Coverage and Actual Checkpoints

| Phase 1 requirement(s) | Reusable pattern | Required actual evidence / actor and stop |
|---|---|---|
| 001 | Full uplift children, proposal §1 | Actual full first packet/equal ORIGINAL; LEAD. No truncated research quote. |
| 002 | Kickoff identity/hierarchy | Real graph identity/schema/permissions/quota, complete 7/41 hierarchy/URLs readback; LEAD/account owner. Destination/team discovery is not materialization. |
| 003 | Second full XML, dispatch idempotency | Actual scoped n1 dispatch/live links; no fake jobs/signatures/duplicate launch. |
| 004-005 | Inventory observer/subject/results | Reuse parent listeners/node proof, establish authorized account relation and bounded actual role/config; INFRA/account owner. Not adoption/deployment/retirement authority. |
| 006-007 | External native Bot/file-I/O | Real self-UUID/path binding/private preserved-byte write/readback equality; human/Bot. No local source substitute. |
| 008 | Same-seat load/fallback, versioned MCP | Working authorized real client/transport, delivered notification/refresh or demonstrated non-support plus exercised fallback; human/SYSTEMS. Access/delivery missing means checkpoint, not new server or client blame. |
| 009-010 | Existing inventory manual account evidence | Actual authenticated team/tier/effective team/group policy; team admin. Timeout/public docs establish neither tier nor mode. |
| 011 | Separate QUALITY ticket/source/receipt | Real §13 result, proper integration/base, independent final-SHA non-commit review; parent/QUALITY/reviewer. No foreign LEAD edit/self-approval. |
| 012 | Non-secret custody/availability | Actual Play/Apple metadata from owners/INFRA. No keys/new credentials/API edits. Verified absence can satisfy honest inventory but blocks later mobile work. |
| 013 | Service-correlated runtime metadata | Actual API version/provider/model/dimensions before Desk storage; SYSTEMS/runtime owner. Image 0.9.1/public health/proposal v0.10.1-slim are distinct; no invented endpoint/upgrade/retain/migration. |
| 014 | Root/trusted-base/current receipt | Actual workflow/event/SHA/run/runner for activation; INFRA/platform/Main. Declaration is not green CI. |
| 015 | Actual account integration, polling floor | Real trigger availability; authorized team owner. No Test Run/activation. Keep ten-minute intake fallback. Parent correction keeps `desk-held-poll` unconditionally every ten minutes; event alternative is only for `desk-intake-poll`. |
| 016 | Ordered owners/contract consumers | Actual final candidate path/actor/consumer review and Main's G-1 checks. Foreign/unowned remain failures; QUALITY owns new uncovered downstream-path decisions. |

All 16 remain pending actual acceptance. Human deferral is a resumable stop, never waiver/pass/Phase 2 clearance. Later account-UI installation/activation, Team-only publication, fresh recipient/mobile, destructive/deploy permission and independent-review gates remain intact.

## No Analog Found

### Artifact-Format Gaps

| File family | Role / Data Flow | Gap / planner action |
|---|---|---|
| `01-NN-PLAN.md` | config; transform/checkpoints | No tracked prior GSD plan returned in inspected phase scope. Installed format plus tracked ticket semantics; independent real bindings. |
| `01-VALIDATION.md` | test; batch/manual | No tracked prior validation document. Extend actual parent-seeded draft; gate tests are rejection support, not live proof. |
| `01-NN-SUMMARY.md` | utility; batch/transform | No tracked summary precedent. Conditional installed-convention output after actual plan completion. |
| `01-VERIFICATION.md` | test; batch/manual | No tracked phase-verification precedent. Installed format with actual verifier/manual evidence and unresolved limits. |

### Live/Access Gaps — No Invented Product Files

- No repository analog proves real participating Bot UUID/own-file write/readback, authenticated SaaS notification/fallback or effective Cursor account settings. Actual external subjects/checkpoints are mandatory.
- Opened inputs establish no complete live graph map, graph identity, quota/write authority or supplied signed assignment/bus signature. Source destinations and parent discovery are bounded.
- No actual private mobile availability record, Hindsight effective version/model/dimensions, current remote CI run/runner evidence or working no-new-tip approval resolver was established here.
- Exact-SHA independent review is specified, not proved available/cleared. Historical approval values/committing stamps cannot substitute.
- Companion current-source applicability is unproved by older maps. Preserve dirty checkout/user work and route later owners.

## Metadata and Handoff

**Search scope:** Existing skills/vendor kickoff, proposal/operating/ownership/security/handoff/receipt definitions, two tracked receipt examples, gate source/tests, root workflow and bounded gateway/custody sections. Search stopped with five strong exemplars: proposal tables, LEAD model, QUALITY model, owned-ticket protocol and gate-test structure; named cross-cutting sources supply existing guards, not another architecture.  
**Files read:** 34 repository inputs/supporting-source files, plus relevant installed GSD skill/templates/checkpoint guidance. Large gate-test sections were located before targeted extraction.  
**Tracking:** Read-only git-index provenance lookups. Installed templates were tool conventions; tracked origin for installed validation template was not established. Fresh planning inputs are not claimed tracked precedents.  
**Mapping date:** 2026-10-08.  
**Mapper verification:** No tests/build/lint/formatters/validation gates/smoke/runtime probes/install/external mutations/deploy/commit/push. Reads/index provenance are not gate passes.  
**Main's later checks:** Once owned slices land, existing relevant/full gate suite, applicable consolidated G-1–G-7/security and artifact/traceability/link checks with actual actor/base/receipt. Separately obtain real manual/live evidence and independent exact-final-SHA review. No artificial echoes or draft-validation clearance.  
**Only mapper write:** `.planning/phases/01-inventory-and-prove-assumptions/01-PATTERNS.md`.  
**Ready for independent planning:** Yes. **Phase verified / downstream cleared:** No.
