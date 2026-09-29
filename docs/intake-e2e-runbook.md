# Intake E2E runbook

**Audience:** Programming Lead re-running intake without tribal knowledge.  
**Graph this smoke records:** `ut-tltyh4-ebc71dbb`  
**Repo:** `https://github.com/swcstudiospace/programming-desk` (transferred from `SomeRandmGuyy/programming-desk`).  
**Runtime for this smoke:** `cursor-cloud` (Lane A). Notion `Agent` default is `cursor-cloud`. Linear team is Spectrum Web Co.  
**Density on this graph:** 5 GoT nodes × 4 CoT steps (5 Linear issues + 20 sub-issues). The second-uplift `<ISSUES>` block has no `<TRACKER_GAPS>` child.  
**Status:** Operator procedure for one docs-only pipeline smoke. A draft PR is the GitHub outcome. This document does not claim Greptile clean, a QUALITY verdict, or merge.

Policy: `docs/gotxcot-cloud-pipeline.md`. GitHub source of truth and lanes: `docs/github-sot-orchestration.md`. Procedure: `skills/gotxcot-uplift`, then `skills/trackplan-dispatch`. Lane B tool names are below, and the Lane B control plane now has its own pages: [`vps-agent-bus.md`](./vps-agent-bus.md) (tools, stop rules, honest gaps) and `skills/agent-bus` (dispatch procedure). Both are LEAD-owned per `ownership.yaml`. They describe the HTTP Agent Bus on connected `user-hermes-agent` only — stdio `user-hermes` stays uninstalled.

---

## Overview and when to use

Use this runbook when an operator drops a real build, fix, research, or change on LEAD and the work must travel the live intake path before anyone writes product code:

1. First uplift (long nested XML).
2. Graph of Thought, 5–8 nodes.
3. Chain of Thought, 4–8 steps per node, one node at a time.
4. Notion Agent Task Graph + Linear Spectrum Web Co.
5. Second uplift that injects live URLs into `<ISSUES>`.
6. `skills/trackplan-dispatch` Lane A (Cursor Cloud Agent) to a **draft** PR.

Graph ID is the idempotency key (`ut-<base36>-<uuid8>`). Find-or-create the Notion Task. Issues key on Graph ID + `nodeId`. Sub-Issues key on Graph ID + `nodeId` + `step`. Re-entry updates rows. It does not create a second Task or a second Linear/Notion set for the same id.

**This graph is already materialized.** `ut-tltyh4-ebc71dbb` has a Notion Task, five Issues, and twenty Sub-Issues. URLs are in [Worked tracker map](#worked-tracker-map-graph-ut-tltyh4-ebc71dbb). Do not run kickoff create again for this id. If a URL is missing on a later read, record `<TRACKER_GAPS>` and the Lead receipt. Do not synthesize a replacement link.

Do not use this runbook for:

- Trivial acks (`ok`, `lgtm`, `thanks`). They do not enter the pipeline (`docs/gotxcot-cloud-pipeline.md`).
- A second-uplift XML that already has live URLs and only needs dispatch. Go to `skills/trackplan-dispatch`.
- Specialist implementation. Seats execute owned tickets. They do not re-run GoT.
- A merge claim, a Greptile-clean claim, or a “done” report to Ove from tracker state. GitHub (branch, draft PR, receipts) is the contract of record (`docs/github-sot-orchestration.md`). PD-1 and PD-6: say what was not run.

Success for **this** docs-only smoke is narrower than full pipeline success:

- `docs/intake-e2e-runbook.md` exists on a draft PR branched from `main`.
- The runbook covers the six sections in this file (overview, stage map, lanes, receipt checklist, ownership, failure modes).
- The diff stays on `docs/intake-e2e-runbook.md` and `.receipts/bot-00-programming-lead/**`.
- The PR body names `graphId ut-tltyh4-ebc71dbb` and states that the change is pipeline E2E smoke documentation.
- No second tracker create. No Greptile or merge claim.

---

## Stage map

LEAD owns the sequence. Specialists do not re-run uplift. LEAD does not implement product code. Counts and the two-pass rule are locked in `docs/gotxcot-cloud-pipeline.md` and executed by `skills/gotxcot-uplift`.

```
plain operator ask
    → first uplift (long nested XML)
    → GoT 5–8 nodes
    → CoT, one node at a time, 4–8 steps each
    → Notion Agent Task Graph + Linear Spectrum Web Co
    → second uplift (<ISSUES> with live URLs, or <TRACKER_GAPS>)
    → skills/trackplan-dispatch
    → Lane A Cursor Cloud Agent (default) → branch + draft PR + receipt
```

| Stage | What LEAD does | Done when |
|---|---|---|
| 1. Drop prompt in | Keep the operator ask verbatim. Do not shorten it into a ticket yet. | `ORIGINAL` can be copied unchanged into the first uplift. |
| 2. First uplift | `skills/gotxcot-uplift` §1. One root: `BUILD_PROMPT`, `FIX_PROMPT`, `RESEARCH_PROMPT`, `CHANGE_PROMPT`, or `UPLIFTED_PROMPT`. Required children include `ORIGINAL`, `SYSTEM_ROLE`, `CONTEXT` or `APP_CONTEXT`, `SCOPE`, `CONSTRAINTS`, `ACCEPTANCE_CRITERIA`, `OUT_OF_SCOPE`. | A senior could hand the XML to a teammate as the spec. Unknown paths stay in `ASSUMPTIONS` / `AMBIGUITIES`. |
| 3. GoT | 5–8 nodes. `n1` kind `understand`, no dependencies. Last node kind `synthesize`. At least one `critique`. Edges only to earlier ids. | Fewer than 5 is rejected and regenerated (or the 5-node fallback in `vendor/ultrathink-policy/constants.ts`, marked fallback). More than 8 is clamped to 8. |
| 4. CoT | **Sequential default** (`concurrency = 1`). Fill one node, then the next, in topological order. Each node: 4–8 numbered steps, one or two sentences, a discrete finding or action. | Each step will become one Linear sub-issue and one Notion Sub-Issue. A single paragraph is not done. |
| 5. Kickoff | Notion collection 🧩 Agent Task Graph (`collection://be3418f0-d2d8-411b-8677-fa8a95ee63be`). Linear team Spectrum Web Co. One issue per node, one sub-issue per step. `Agent` = `cursor-cloud` for Lane A. Checklist concepts: `vendor/ultrathink-policy/kickoff-checklist.md`. | Every created row has a URL, or the failed `nodeId` / `step` is on a gap list. One create failure does not drop the rest. |
| 6. Second uplift | Extend the first XML. Inject `<ISSUES>` **inside** the root. Task, every Issue, every Sub-Issue carry the live Notion and Linear URLs from stage 5. Fold non-blocking defaults into `<CLARIFICATIONS>`. | The XML is longer than the first pass. URLs are the ones just created. Omitted rows are `<TRACKER_GAPS>`, not silent holes and not placeholders. |
| 7. Dispatch | `skills/trackplan-dispatch` sends that XML plus the GitHub work packet. This smoke uses Lane A. | Cloud Agent launch is recorded in the Lead receipt (agent id, or an honest blocker). Outcome on GitHub is a **draft** PR. Do not poll to completion. Do not claim merge. |

Parallel CoT is allowed only when the runtime caps concurrency, nodes in the same dependency level do not need each other’s conclusions, and a failure in one node is still reported. It is not the default.

Compact Linear (`ultrathink-linear-got-cot`: one parent plus one child per node, CoT as body text) is quota-fallback only. It requires an explicit Lead decision recorded on the Task after `USAGE_LIMIT_EXCEEDED` or an equivalent hard cap. Do not flip the skill or `docs/gotxcot-cloud-pipeline.md` silently.

Desk policy overrides the unpatched VPS engine (`MIN_NODES = 3`, GoT prompt “4 to 8”, `MIN_STEPS = 5`) until `vendor/ultrathink-policy/` is applied on the VPS. Dispatch still requires 5–8 `<ISSUE>` elements in the XML unless `<TRACKER_GAPS>` records a real create failure.

### Stage 6 — `<ISSUES>` shape

```xml
<ISSUES>
  <TASK graphId="ut-…" notionUrl="https://www.notion.so/…">Task title</TASK>
  <ISSUE nodeId="n1" notionUrl="https://www.notion.so/…" linearId="SPE-…" linearUrl="https://linear.app/…">[n1] Title</ISSUE>
  <SUBISSUE nodeId="n1" step="1" notionUrl="https://www.notion.so/…" linearId="SPE-…" linearUrl="https://linear.app/…">[n1] Step 1: …</SUBISSUE>
</ISSUES>
<TRACKER_GAPS>
  <!-- only when a create failed; otherwise omit the element -->
</TRACKER_GAPS>
```

Copy URLs from the kickoff result. The worked map below is the copy for `ut-tltyh4-ebc71dbb` only.

### Stage 7 — draft PR, not merge

`skills/trackplan-dispatch` tells the implementer to open a **draft** PR. Branch form from `docs/github-sot-orchestration.md`:

```text
bot-<nn>-<seat>/<task_id>
```

This smoke’s branch is `bot-00-programming-lead/intake-e2e-runbook-ut-tltyh4-ebc71dbb`. Put Graph ID, Linear ids, Notion URLs, `runtime`, `owner`, `task_id`, and `receipt_path` in the PR body. Greptile and the QUALITY merge gate (`skills/greptile-merge-gate`) run after a draft exists. They are not part of dispatch and not part of this docs smoke. PD-3 and PD-6: do not write “Greptile clean” or “merged” to keep the graph moving.

---

## Lane A Cloud Agent and Lane B agent bus

LEAD picks the lane per ticket. Default after the second uplift is Lane A unless the ticket says `runtime=hermes`. Lane C (`SendToAgent` when `ownership.yaml` is already 1:1) is a specialist path, not this smoke. Lanes may compose. Lane B does not bypass G-1…G-6.

| Lane | Runtime | When | Durable output |
|---|---|---|---|
| **A** | Cursor Cloud Agent | Default. Notion `Agent` = `cursor-cloud`. | Branch + draft PR + `.receipts/` on GitHub. |
| **B** | VPS Hermes via `agent_bus_*` on Hermes MCP | Ticket / runtime says `hermes`. | Same GitHub contract. The VPS is a computer, not a source of truth. |
| **C** | Specialist `SendToAgent` | Path ownership is already clear. | Same GitHub contract. LEAD does not write the code. |

### Lane A — this smoke

Preconditions from `skills/trackplan-dispatch`:

1. Idempotency: do not double-launch the same `graphId` plus node subset without an explicit operator request. If agents or open PRs cannot be listed, write `unverified`. Do not assume none exist.
2. Notion Task `Agent` is `cursor-cloud` (set it if kickoff left `claude-code`).
3. The prompt is the work packet plus the **entire** second-uplift XML. Do not truncate `<ISSUES>`.
4. Launch only when the operator intends real work. There is no documented dry-run that still counts as dispatch.

After launch, record the agent id and URL in the Lead receipt. Do not poll to completion. On revival, note branch and draft PR URL if they exist. List `unverified`. Do not claim merge from tracker state.

The implementer respects `ownership.yaml`. If a path is owned by another seat, stop and report the blocker. Do not open a second set of Linear issues. The `<ISSUES>` block is the tracker map.

### Lane B — `agent_bus_*` (no secrets)

`user-hermes-agent` is the live Lane B MCP (HTTP, connected). Preferred tools are `agent_bus_*`. `handoff_to_hermes` is Hermes-only fallback. Local stdio `user-hermes` was intentionally uninstalled on the desk host on 2026-09-24. Agent Bus on `user-hermes-agent` supersedes `hermes-mcp-bridge.mjs`. Do not rebuild that bridge and do not reinstall the stdio server. A failed `agent_bus_*` call stops the lane. Do not paper over it with SSH or chat paste.

Separately, Hermes MCP exposes these tools (descriptors read while authoring this runbook; **none of them were called** for `ut-tltyh4-ebc71dbb`):

| Tool | Role | Arguments |
|---|---|---|
| `agent_bus_health` | Loopback health of local vps-agent-bus. Returns status and available runtimes. Preferred live path versus fire-and-forget `handoff_to_hermes`. | none |
| `agent_bus_start_job` | Start a job (`POST /v1/jobs`). Returns `jobId`, status, and `wsUrl`. MCP does not open the WebSocket. | required `runtime`, `goal`; optional `provider`, `idempotency_key` |
| `agent_bus_get_job` | One job snapshot (`GET /v1/jobs/{id}`). | required `job_id` |
| `agent_bus_wait_job` | Poll until `completed`, `failed`, `error`, or timeout. | required `job_id`; `timeout_sec` default 180 (max 600); `poll_sec` default 2 |

`agent_bus_start_job` reports that the public `wss` URL needs `BUS_TOKEN` and that the token is **not** included in the tool result. Do not paste `BUS_TOKEN` or any other credential into this runbook, the PR body, a receipt, or a work packet. `docs/vps-agent-bus.md` is the operator-named place for env file locations; that file is not in this repo, so this runbook does not invent a path, host, or port. Call the MCP tools. Do not substitute `curl` against an undocumented bus URL.

If the tool is missing, unauthenticated, or errors: **stop**. Record the blocker in the Lead receipt. Do not invent an SSH coding handoff. SSH to the VPS is INFRA-owned ops (`docs/github-sot-orchestration.md`). Do not claim Hermes picked up the job without a tool result or a GitHub draft PR.

Passing `graphId` as `idempotency_key` is optional on the descriptor. This runbook does not claim the server dedupes on it. `skills/trackplan-dispatch` still forbids a second launch of the same `graphId` without an explicit operator request.

`skills/agent-bus` is the operator-named skill path for this lane. It is not in the tree. Until it lands, Lane B procedure in-repo is this section plus `skills/trackplan-dispatch` Lane B and `docs/github-sot-orchestration.md` §5.

---

## Lead receipt checklist

Write `.receipts/bot-00-programming-lead/<task_id>.json` for orchestration LEAD actually performed. Schema combines `skills/verification-receipts` (gate G-2) and the Lead dispatch receipt in `skills/trackplan-dispatch`. This smoke’s file is `.receipts/bot-00-programming-lead/intake-e2e-runbook-ut-tltyh4-ebc71dbb.json`.

`.gitignore` ignores `.receipts/**/*.json`. A receipt that must travel with the PR is force-added (`git add -f`). A checkout that does not contain the file will fail a G-2 “no verification receipt” locate step. Force-add is not a secret-scanner bypass and is not `--no-verify`.

### Fields the checklist requires

| Field | Requirement |
|---|---|
| `task_id` | Matches the branch slug / ticket. |
| `bot` | `bot-00-programming-lead` for a Lead receipt. |
| `started_at` / `completed_at` | ISO-8601 timestamps of work actually done. |
| `graph_id` | `ut-…` from kickoff. This smoke: `ut-tltyh4-ebc71dbb`. |
| `runtime` / `lane` | `cursor-cloud` / `A`, or `hermes` / `B`. |
| `repo` | Full GitHub URL. |
| `node_count` | `<ISSUE>` count in the second uplift (5–8), not a guessed target. |
| `subissue_counts` | Map of `nodeId` → `<SUBISSUE>` count (each 4–8 unless gapped). |
| `linear_ids` / `notion_urls` | Copied from `<ISSUES>`. Omit ids that were not created; list those under gaps. |
| `commands` | Each entry has `cmd` and `exit_code`. `output_tail` is short and contains no secrets. |
| `claims` | Each claim has `evidence_command_index`. A claim that cites a non-zero exit sets `expects_failure: true`. |
| `unverified` | Specific leftovers. An empty array asserts complete verification. Vague entries (`some edge cases`) fail G-2. |
| `agent_id` | Cloud agent id, Hermes job id, or `null` if launch did not happen. |
| `pr_url` | Draft PR URL once it exists; `null` until then. Do not fabricate. |
| `blockers` | Auth failures, ownership stops, quota stops. `[]` only when there are none. |
| `approved_by` | Someone other than the authoring bot. **Do not self-approve.** Leave it unset until QUALITY or a human reviews. G-2 fails closed while it is missing. That failure is information (PD-3). |

G-2 forbids bypass commands (`--no-verify`, `|| true`, `2>/dev/null`, and the rest of the list in `ci/gates/check_receipt.py`). PD-4: a receipt that contains a token is a failed receipt even if every command exited 0.

### Commands to record for a docs smoke

Run these from the repo root and copy the exit code you observed. Do not invent a zero.

```bash
python3 ci/gates/check_secrets.py --files docs/intake-e2e-runbook.md .receipts/bot-00-programming-lead/<task_id>.json
python3 ci/gates/check_ownership.py --bot bot-00-programming-lead --files .receipts/bot-00-programming-lead/<task_id>.json
python3 ci/gates/check_ownership.py --bot bot-00-programming-lead --files docs/intake-e2e-runbook.md
python3 ci/gates/check_receipt.py --receipt .receipts/bot-00-programming-lead/<task_id>.json --bot bot-00-programming-lead
```

Expect `python3 ci/gates/check_ownership.py --bot bot-00-programming-lead --files docs/intake-e2e-runbook.md` to **exit 0**. QUALITY commit `7fd7248` added a last-match rule that assigns that file to `bot-00-programming-lead`. Do not put `expects_failure` on that command. Before `7fd7248` the same command exited 1 (`FOREIGN`, owner `bot-06-quality-security` via `docs/**`). That result is history. The operator procedure is the current manifest: G-1 PASS for this path.

Expect `check_receipt.py` to exit non-zero while `approved_by` is unset. Leave the field unset. Do not stamp it with `bot-00-programming-lead` or with `bot-06-quality-security`. QUALITY sets `approved_by` on this Lead receipt in a follow-up. Do not weaken the gate.

### `unverified` entries that belong on an intake receipt

Name the gap and why:

- Greptile was not triggered; merge was not requested.
- Lane B tools were not called, if the runtime was Lane A.
- Notion/Linear URLs were copied from `<ISSUES>` and not re-fetched, if that is what happened.
- PR → Notion/Linear field sync did not run (that skill is still unbuilt; do not invent tracker rows).
- Any `nodeId` / `step` listed in `<TRACKER_GAPS>`.

---

## Ownership and out of scope

`ownership.yaml` is last-match. Broad `docs/**` and `skills/**` stay `bot-06-quality-security`. Later rules give LEAD `docs/desk-operating-model.md`, `docs/gotxcot-cloud-pipeline.md`, `docs/github-sot-orchestration.md`, and — since QUALITY commit `7fd7248` — **`docs/intake-e2e-runbook.md`**, `docs/vps-agent-bus.md`, and `skills/agent-bus/**`. `skills/greptile-merge-gate/**` stays QUALITY because that rule comes after the Lead section.

G-1 for `bot-00-programming-lead` on `docs/intake-e2e-runbook.md` **passes**. Do not tell an operator to expect a nonzero result, and do not attach `expects_failure` to that check. Before `7fd7248` the file matched only `docs/**` and the same check failed `FOREIGN`. Record that only when you are describing history.

`.receipts/bot-00-programming-lead/**` is `bot-00-programming-lead`. `ownership.yaml` itself stays `bot-06-quality-security`. This follow-up does not edit the manifest. Greptile P2 on the agent-bus forward rules is waived by QUALITY; the waive receipt is theirs, under `.receipts/bot-06-quality-security/`, and is not written here.

| Path | Owner | This smoke |
|---|---|---|
| `docs/intake-e2e-runbook.md` | `bot-00-programming-lead` via last-match override (`7fd7248`) | In scope. G-1 PASS for bot-00. |
| `docs/vps-agent-bus.md` | `bot-00-programming-lead` via last-match override (`7fd7248`) | Pattern kept. File is not on this branch. Do not narrow the rule. |
| `skills/agent-bus/**` | `bot-00-programming-lead` via last-match override (`7fd7248`) | Pattern kept. Directory is not on this branch. Do not narrow the rule. |
| `.receipts/bot-00-programming-lead/**` | `bot-00-programming-lead` | In scope. |
| `skills/gotxcot-uplift/**`, `skills/trackplan-dispatch/**` | `bot-00-programming-lead` | Cited, not edited. |
| `skills/greptile-merge-gate/**` | `bot-06-quality-security` | Not edited. |
| `skills/**` (other) | `bot-06-quality-security` | Not edited. |
| `ownership.yaml` | `bot-06-quality-security` | Changed by QUALITY in `7fd7248`. Not changed in this follow-up. |
| `services/**` | `bot-01-systems-backend` | Out of scope. |
| `web/**` | `bot-02-web-edge` | Out of scope. |
| `android/**` | `bot-03-android` | Out of scope. |
| `ios/**` | `bot-04-ios` | Out of scope. |
| `infra/**` | `bot-05-infrastructure` | Out of scope. |

Also out of scope: product features, Greptile merge claims, the VPS ultrathink engine patch, rebuilding the stdio `hermes-mcp-bridge`, specialist path edits, and creating another Linear or Notion issue set for `ut-tltyh4-ebc71dbb`.

---

## Failure modes

Record the failure in `<TRACKER_GAPS>` (when the miss is a tracker row) and in the Lead receipt `unverified` / `blockers`. Do not invent a URL, a node count, or a green gate to hide it.

| Mode | What you observe | What to record | What not to do |
|---|---|---|---|
| **TRACKER_GAPS** | Kickoff did not return a Notion or Linear URL for a Task, Issue, or Sub-Issue. | Sibling `<TRACKER_GAPS>` with `nodeId` and `step`. Receipt lists the same pairs. Dispatch may proceed only for rows that have URLs; say which nodes were withheld. | Placeholder links (`https://…`, `SPE-…` with no real id). Dropping the rest of the node after the first error. Creating a second issue set “to fill the holes.” |
| **Auth (Notion / Linear)** | Create or fetch returns unauthorized / needs auth. | Blocker: which surface, which call, no token text. Rows that were not created go to `TRACKER_GAPS`. | Pasting connector tokens into the runbook, PR, or receipt. Inventing URLs from memory. |
| **Auth (Lane B)** | `agent_bus_*` missing, unauthorized, or erroring. | Stop. `runtime` stays unlaunched. `agent_id` null. Blocker names the tool and the error class, not `BUS_TOKEN`. | SSH coding handoff. Rebuilding `hermes-mcp-bridge.mjs` or reinstalling stdio `user-hermes`. Chat-paste as the durable record. Claiming the Hermes job started. |
| **Auth (Greptile)** | `get_me` or `trigger_code_review` needs auth. | `unverified`: Greptile not run. LEAD escalates. Merge claim stays blocked. | Silent skip. “Greptile clean.” Waiving without a QUALITY-acknowledged waiver receipt (`skills/greptile-merge-gate`). |
| **Density, too small** | GoT returns fewer than 5 nodes, or a node has fewer than 4 steps, and this was not an explicit fallback. | Reject and regenerate. If the 5-node fallback is used, mark graph source `fallback`. Do not dispatch an XML with fewer than 5 `<ISSUE>` elements unless `<TRACKER_GAPS>` explains a real create failure. | Shipping a 3- or 4-node graph “to save time.” Collapsing steps into one sub-issue. |
| **Density, too large** | Model returns more than 8 nodes or more than 8 steps. | Clamp nodes to 8 by merging the least load-bearing middle nodes. Keep steps inside 4–8. | Silently keeping 9+ nodes or 9+ steps. |
| **Quota** | Linear `USAGE_LIMIT_EXCEEDED` (or equivalent hard cap) on Spectrum Web Co. Dense multiplies rows: `nodes × (1 + steps)` plus parents. | Stop creating. Surface the error and the missing pairs in the receipt and `<TRACKER_GAPS>`. Escalate to the operator for a plan upgrade **or** an explicit one-run compact override recorded on the Task. | Silent compact. Claiming rows that were not created. |
| **Ownership** | G-1 `FOREIGN` or `UNOWNED` for a path the acting bot does not own. `docs/intake-e2e-runbook.md` is not that case: bot-00 PASS after `7fd7248`. | Non-zero exit, with `expects_failure`, only when the manifest still reports FOREIGN. Name the owner. A PASS on the runbook is exit 0 and is not an `expects_failure` claim. | Narrowing the `7fd7248` agent-bus rules to silence Greptile P2. Weakening G-1. Editing `services/`, `web/`, `android/`, `ios/`, or `infra/`. |
| **Secrets** | A token, including `BUS_TOKEN`, is about to be written down. G-3 would scan the diff. | Omit the value. Point at `docs/vps-agent-bus.md` only when that file exists. | Committing the secret and rotating later as the plan. `# pragma: allowlist secret` to hide a real credential (PD-3, PD-4). |
| **Over-claim** | Prose says the pipeline is verified end-to-end, Greptile is clean, or the PR merged. | Rewrite to draft-PR plus `unverified`. `docs/gotxcot-cloud-pipeline.md` and `docs/github-sot-orchestration.md` both state E2E is not verified. | Weakening G-1…G-6 or PD-1…PD-6 so the smoke looks finished. |

This graph’s second uplift has 5 issues and 20 sub-issues and no `<TRACKER_GAPS>` element. That is a property of the packet that was supplied. It is not a new live create, and it is not proof the URLs still resolve.

---

## Worked tracker map (graph `ut-tltyh4-ebc71dbb`)

Copied from the second-uplift `<ISSUES>` block for this smoke. Notion Task: [Agent Task Graph row](https://www.notion.so/3e4bc1a0c7ae81d3aa4ae3dd210969f7). Title: `[E2E] Intake runbook ut-tltyh4-ebc71dbb`.

| Node | Linear | Notion |
|---|---|---|
| n1 Understand intake E2E runbook need | [SPE-140](https://linear.app/swcstudio/issue/SPE-140/ut-tltyh4-ebc71dbbn1-understand-intake-e2e-runbook-need) | [Issue](https://app.notion.com/p/3e4bc1a0c7ae81948ecac6175754a3cd?pvs=204) |
| n2 Decompose runbook structure and ownership | [SPE-137](https://linear.app/swcstudio/issue/SPE-137/ut-tltyh4-ebc71dbbn2-decompose-runbook-structure-and-ownership) | [Issue](https://app.notion.com/p/3e4bc1a0c7ae81718ee4cd3734e57bec?pvs=204) |
| n3 Generate runbook content outline | [SPE-139](https://linear.app/swcstudio/issue/SPE-139/ut-tltyh4-ebc71dbbn3-generate-runbook-content-outline) | [Issue](https://app.notion.com/p/3e4bc1a0c7ae81d0b151d10c0f4be6b8?pvs=204) |
| n4 Critique gaps vs live pipeline | [SPE-141](https://linear.app/swcstudio/issue/SPE-141/ut-tltyh4-ebc71dbbn4-critique-gaps-vs-live-pipeline) | [Issue](https://app.notion.com/p/3e4bc1a0c7ae818a82cafa67136a8908?pvs=204) |
| n5 Synthesize implementable work units | [SPE-138](https://linear.app/swcstudio/issue/SPE-138/ut-tltyh4-ebc71dbbn5-synthesize-implementable-work-units) | [Issue](https://app.notion.com/p/3e4bc1a0c7ae816eb669e670b2a07af5?pvs=204) |

Sub-issues (4 per node):

| Node | Step | Linear | Notion |
|---|---|---|---|
| n1 | 1 | [SPE-145](https://linear.app/swcstudio/issue/SPE-145/understand-intake-e2e-runbook-need-step-1-list-the-operator-smoke-ask) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae817cb71fe4279fd2c8e1?pvs=204) |
| n1 | 2 | [SPE-144](https://linear.app/swcstudio/issue/SPE-144/understand-intake-e2e-runbook-need-step-2-name-each-pipeline-stage) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae81b4a2dcdbb12a3090a2?pvs=204) |
| n1 | 3 | [SPE-142](https://linear.app/swcstudio/issue/SPE-142/understand-intake-e2e-runbook-need-step-3-note-lane-a-default-vs-lane) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae816a81f9d6d45be4aba7?pvs=204) |
| n1 | 4 | [SPE-143](https://linear.app/swcstudio/issue/SPE-143/understand-intake-e2e-runbook-need-step-4-record-what-success-looks) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae8190a154c52c43777b8f?pvs=204) |
| n2 | 1 | [SPE-159](https://linear.app/swcstudio/issue/SPE-159/decompose-runbook-structure-and-ownership-step-1-map-required-sections) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae81ebbf16fb4a9761b573?pvs=204) |
| n2 | 2 | [SPE-160](https://linear.app/swcstudio/issue/SPE-160/decompose-runbook-structure-and-ownership-step-2-confirm-docs-and) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae81e486f2d3803a22a693?pvs=204) |
| n2 | 3 | [SPE-153](https://linear.app/swcstudio/issue/SPE-153/decompose-runbook-structure-and-ownership-step-3-list-out-of-scope) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae81ed8a96e3d7ccdc09c1?pvs=204) |
| n2 | 4 | [SPE-152](https://linear.app/swcstudio/issue/SPE-152/decompose-runbook-structure-and-ownership-step-4-define-receipt-fields) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae81a2bb62fa182e1c6382?pvs=204) |
| n3 | 1 | [SPE-155](https://linear.app/swcstudio/issue/SPE-155/generate-runbook-content-outline-step-1-draft-overview-including-when) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae813b9ac7fffd4efb2f16?pvs=204) |
| n3 | 2 | [SPE-146](https://linear.app/swcstudio/issue/SPE-146/generate-runbook-content-outline-step-2-draft-stage-map-with-density) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae81368974c7c918cfa605?pvs=204) |
| n3 | 3 | [SPE-161](https://linear.app/swcstudio/issue/SPE-161/generate-runbook-content-outline-step-3-draft-lane-a-cloudagent-and) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae812ca9e4ee37ae1f7f13?pvs=204) |
| n3 | 4 | [SPE-150](https://linear.app/swcstudio/issue/SPE-150/generate-runbook-content-outline-step-4-draft-failure-mode-table) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae817db879d801612f3e0b?pvs=204) |
| n4 | 1 | [SPE-158](https://linear.app/swcstudio/issue/SPE-158/critique-gaps-vs-live-pipeline-step-1-check-for-any-greptilemerge) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae8165b36ddefb883473dc?pvs=204) |
| n4 | 2 | [SPE-156](https://linear.app/swcstudio/issue/SPE-156/critique-gaps-vs-live-pipeline-step-2-ensure-bus-token-and-connector) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae8166ae25dc5d7eb2488f?pvs=204) |
| n4 | 3 | [SPE-149](https://linear.app/swcstudio/issue/SPE-149/critique-gaps-vs-live-pipeline-step-3-verify-the-doc-points-to-gotxcot) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae81d083b9c232124cbc04?pvs=204) |
| n4 | 4 | [SPE-148](https://linear.app/swcstudio/issue/SPE-148/critique-gaps-vs-live-pipeline-step-4-confirm-draft-pr-only-language) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae810c8837f091b27a1b68?pvs=204) |
| n5 | 1 | [SPE-154](https://linear.app/swcstudio/issue/SPE-154/synthesize-implementable-work-units-step-1-unit-a-write-docsintake-e2e) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae817581b9e7ee9cb1259e?pvs=204) |
| n5 | 2 | [SPE-157](https://linear.app/swcstudio/issue/SPE-157/synthesize-implementable-work-units-step-2-unit-b-optional-lead) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae815bbc11de6092275f4f?pvs=204) |
| n5 | 3 | [SPE-151](https://linear.app/swcstudio/issue/SPE-151/synthesize-implementable-work-units-step-3-unit-c-open-draft-pr-from) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae810ba269e0b1f4cb3459?pvs=204) |
| n5 | 4 | [SPE-147](https://linear.app/swcstudio/issue/SPE-147/synthesize-implementable-work-units-step-4-unit-d-list-unverified) | [Sub-Issue](https://app.notion.com/p/3e4bc1a0c7ae81778c35c6d3a136e112?pvs=204) |

---

## Unverified for this smoke

- Live page fetches of the Notion and Linear URLs above were not re-run while writing this file. The map is a copy of the supplied `<ISSUES>` block.
- `agent_bus_health`, `agent_bus_start_job`, `agent_bus_get_job`, and `agent_bus_wait_job` were not invoked. No Lane B job id exists for this graph in this receipt.
- `skills/agent-bus` and `docs/vps-agent-bus.md` are not on `origin/main`. Env file location for `BUS_TOKEN` is therefore not documented here.
- Greptile review 26348840 completed at `becec09` with confidence 3/5. That is not a clean review and not a merge claim. This follow-up does not re-trigger Greptile.
- `approved_by` on the Lead receipt is `bot-06-quality-security`, set by QUALITY. LEAD did not self-approve. The P2 ownership-scope waive receipt is `.receipts/bot-06-quality-security/greptile-p2-waiver-ownership-scope-pr4.json`.
- G-1 for `bot-00-programming-lead` on `docs/intake-e2e-runbook.md` passes under the `7fd7248` carve-out. The pre-carve-out FOREIGN result is historical only.
- PR → Notion/Linear sync was not run. No tracker rows were created or updated by this change.
- The VPS `claude-ultrathink` constant patch was not done. The stdio `hermes-mcp-bridge` was not rebuilt. Desk policy after 2026-09-24 is that `user-hermes` stays uninstalled; do not rebuild the bridge.
