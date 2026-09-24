# GoTxCoT Cloud Pipeline — Double Uplift → Dense Trackers → Cursor / Hermes

**Locked:** 2026-09-24 (Sydney), density revised for the Programming Desk pack.  
**Linear density:** **Dense** (desk default). Compact is quota-fallback only.  
**Audience:** Programming Lead wiring operator intake to trackers and a runtime lane.  
**Status:** Desk policy encoded in this repo (docs + `skills/gotxcot-uplift` + `skills/trackplan-dispatch` + `vendor/ultrathink-policy`). The upstream `claude-ultrathink` engine lives on the VPS and is **not** in this repository. **E2E launch → PR → Greptile → QUALITY is not verified** in this pack. Hermes lane remains blocked until auth/bridge work (see [`github-sot-orchestration.md`](./github-sot-orchestration.md)).

**Runtime / GitHub SoT:** Planning overlays (Linear + Notion) feed execution. **GitHub (branch, PR, checks, review) is the contract of record.** Cursor Cloud Agent is the default runtime. Optional VPS Hermes is a runtime lane, not a second source of truth.

---

## Locked decisions

| Rule | Value |
|---|---|
| Seats | Seven. **LEAD sits in** the Programming Desk channel with SYSTEMS, WEB, ANDROID, IOS, and INFRA. **QUALITY is off-channel** (post-build merge-gate). Platform max is 6. |
| GoT nodes | **5–8** per real build task. Never fewer than 5. Clamp maximum **8**. |
| CoT steps | **4–8 discrete steps per node** (plural; more than one). Each step is one Linear **sub-issue** and one Notion **Sub-Issue**. |
| CoT fill | **Sequential by default** (one node at a time) because of API rate limits. Parallel fill is allowed only when the runtime can do it safely. |
| Linear issue | **One per GoT node** |
| Linear sub-issue | **One per CoT step** |
| Uplift passes | **Two.** First rewrite before the graph. Second rewrite after trackers exist, injecting live URLs. |
| Notion collection | **🧩 Agent Task Graph** (`collection://be3418f0-d2d8-411b-8677-fa8a95ee63be`) |
| Notion `Agent` | **`cursor-cloud`** when Cursor Cloud Agents run the work |
| Dispatch | Final second-uplift XML → **Cursor Cloud Agent (default)** or **Hermes** via `skills/trackplan-dispatch` |
| Compact policy | `ultrathink-linear-got-cot` — **not** the desk default. Explicit Lead decision only, after a quota failure. |
| Code / merge | GitHub. Linear and Notion are planning overlays. |
| Merge gate | Greptile stays on QUALITY. Do not weaken G-1…G-6 or PD-1…PD-6. |

Do not recommend compact as the default. Switching requires an explicit Lead decision recorded on the Task, not a silent reversion in a skill.

Upstream constants today (VPS `claude-ultrathink`) still say `MIN_NODES = 3` and a GoT prompt of "4 to 8 nodes", with `MIN_STEPS = 5`. **Desk policy overrides that** until the VPS copy is patched. Exact diffs: [`vendor/ultrathink-policy/README.md`](../vendor/ultrathink-policy/README.md).

---

## End-to-end flow (authoritative)

Programming Lead owns this sequence. Specialists do not re-run uplift. LEAD does not implement product code.

```
1. Drop prompt in          plain operator ask (Ove → LEAD)
        │
        ▼
2. First uplift            long nested XML
        BUILD_PROMPT | FIX_PROMPT | RESEARCH_PROMPT | CHANGE_PROMPT | UPLIFTED_PROMPT
        ORIGINAL, SCOPE, ACCEPTANCE_CRITERIA, CONSTRAINTS, …
        │
        ▼
3. Graph of Thought        5–8 nodes (major work units). Clamp [5, 8].
        │
        ▼
4. Chain of Thought        one node at a time (default)
        each node → 4–8 discrete steps
        │
        ▼
5. Materialize trackers    Notion Task (Kanban) + Issue per node + Sub-Issue per step
                           Linear issue per node + sub-issue per step
                           linked under the Notion Task. Idempotent on Graph ID.
        │
        ▼
6. Second uplift           rewrite/extend the first XML; inject <ISSUES>
                           with live Notion + Linear URLs for Task, every Issue, every Sub-Issue
                           result is extremely long and XML-tag dense
        │
        ▼
7. Dispatch                skills/trackplan-dispatch
                           Cursor Cloud Agent (default) or Hermes
                           Notion Agent = cursor-cloud on Lane A
        │
        ▼
   Specialists execute owned tickets → receipts
        │
        ▼
   QUALITY (G-1…G-6 + Greptile merge gate) → LEAD sync → report to Ove
```

| Stage | Owner | What happens |
|---|---|---|
| **1. Drop prompt in** | LEAD | Accept the plain operator ask. Do not paraphrase it into a short ticket yet. Trivial acks (`ok`, `lgtm`) do not enter this pipeline. |
| **2. First uplift** | LEAD (`skills/gotxcot-uplift`) | Rewrite into production-grade nested XML. Long and tag-dense. Preserve ORIGINAL verbatim. Do not invent repo facts. |
| **3. GoT** | LEAD | **5–8 nodes** sized to task complexity. First node `understand`, last node `synthesize`. Real build tasks never ship a 3- or 4-node graph. |
| **4. CoT** | LEAD | Fill **one node at a time** unless parallel fill is explicitly safe. Each node’s rationale is **4–8 numbered steps**. Each step is a discrete unit, not a sentence fragment. |
| **5. Materialize** | LEAD (kickoff checklist) | Notion Agent Task Graph + Linear Spectrum Web Co. One issue per node, one sub-issue per step. Record every URL. One create failure must not drop the rest. |
| **6. Second uplift** | LEAD | Take the first-uplift XML and extend it so `<ISSUES>` (Task, Issue, Sub-Issue) carries **live** Notion and Linear URLs. Do not substitute a short appendix or a markdown table. |
| **7. Dispatch** | LEAD (`skills/trackplan-dispatch`) | Feed that final XML to Cursor Cloud Agent by default, or Hermes when `runtime=hermes`. |
| **8. Specialist work** | SYSTEMS / WEB / ANDROID / IOS / INFRA | Execute only owned paths named on the ticket. Write receipts under `.receipts/<bot>/`. Do not invent tracker rows. |
| **9. QUALITY** | QUALITY | Independent review. G-1…G-6. Greptile merge gate. No bypass. |
| **10. Sync + report** | LEAD | Mirror PR fields onto the existing Notion Task / Linear state. Never invent new tracker rows. Report receipts, QUALITY verdict, and honest `unverified` to Ove. |

Upstream `claude-ultrathink` stops at Claude Code `Task` subagents and appends `<ISSUES>` after kickoff. Desk execution target is **Cursor Cloud Agent** (Hermes optional). The **second uplift** is a desk pass: URLs are injected into the specification the runtime actually receives.

---

## Stage 2 — First uplift (XML density bar)

Follow `skills/gotxcot-uplift`. The engine prompt this pass mirrors is upstream `UPLIFT_SYSTEM_PROMPT` (`src/uplift/prompt.ts` on the VPS).

Pick **exactly one** root:

| Root | Use |
|---|---|
| `BUILD_PROMPT` | New feature, page, flow, or capability |
| `FIX_PROMPT` | Bug, regression, broken behavior |
| `RESEARCH_PROMPT` | Investigate, explain, compare, explore |
| `CHANGE_PROMPT` | Refactor, rename, migrate, restyle, adjust existing behavior |
| `UPLIFTED_PROMPT` | None of the above fits cleanly |

Required children (SCREAMING_SNAKE), all present, all substantive:

- `ORIGINAL` — the operator ask **verbatim**, not a paraphrase
- `SYSTEM_ROLE`
- `CONTEXT` or `APP_CONTEXT`
- `SCOPE`
- `CONSTRAINTS` — include: do not invent repository facts
- `ACCEPTANCE_CRITERIA` — observable, testable
- `OUT_OF_SCOPE`

Add when the work needs them: `PLATFORM_CONSTRAINTS`, `DESIGN_SYSTEM_CONTINUITY`, `SECURITY_AND_VALIDATION`, `GRACEFUL_DEGRADATION`, `STATES`, `WORKFLOW`, `ASSUMPTIONS`, `AMBIGUITIES`, and **named nested sections** shaped like the surfaces in the ask (not `<item>` soup).

**Density bar:** a senior would hand this to a teammate as the spec. A 10-field stub or a one-paragraph paraphrase fails the pass. Unknown file paths, versions, and API routes go in `ASSUMPTIONS` / `AMBIGUITIES`, never as facts.

Fail-open: if the rewrite model fails, wrap the original and say the uplift source is `fallback`. Do not pretend a short wrap is a dense spec.

---

## Stage 3 — Graph of Thought (5–8 nodes)

Each node is a **major work unit**, not a checkbox.

| Constraint | Rule |
|---|---|
| Count | **5 minimum, 8 maximum.** Scale with complexity inside that band. A real build task does not use 3 or 4 nodes. |
| Shape | DAG. `id` = `n1`…`nN`. `depends_on` only earlier ids. Independent nodes stay independent. |
| Ends | First node kind `understand` (no dependencies). Last node kind `synthesize` (ordered execution plan). |
| Coverage | Understanding, decomposition, options, risks, and a final plan. At least one `critique` node for missing information that would change the implementation. |
| Specificity | Questions name this task. Do not paste a generic template and stop. |
| Out of the graph | Do not plan Linear issues, GitHub PRs, Greptile, or the specialist swarm inside the graph itself. Seats are chosen later from `ownership.yaml`. |

Node kinds: `understand`, `decompose`, `generate`, `compare`, `critique`, `aggregate`, `refine`, `synthesize`.

If the model returns fewer than 5 nodes, **reject and regenerate** (or apply the 5-node fallback graph in `vendor/ultrathink-policy/constants.ts` and mark the graph source as fallback). If it returns more than 8, **clamp to 8** by merging the least load-bearing middle nodes — do not silently keep 9+.

---

## Stage 4 — Chain of Thought (4–8 steps, sequential default)

Run CoT **one node at a time**, in topological order. That is the desk default (`concurrency = 1` in upstream `runThink`). API rate limits are the reason.

Parallel fill is allowed only when:

- the runtime can cap concurrency, and
- nodes in the same dependency level do not need each other’s conclusions, and
- a failure in one node is still reported rather than dropping the rest.

Each node’s `<rationale>` contains **4–8 numbered steps**. Each step:

- is one or two sentences,
- is a discrete finding or action,
- becomes **one Linear sub-issue** and **one Notion Sub-Issue**,
- is not a clause chopped out of a longer sentence.

A node with a single paragraph and no numbered steps is not done. Collapsing “step 1–6” into one sub-issue violates Dense.

`<conclusion>` is the node’s answer. On `synthesize`, include a WORKFLOW of file-disjoint units. On `critique`, end with `Open questions:` (or `Open questions: none`). HITL still caps blocking questions at **4**.

---

## Stage 5 — Materialize trackers (dense)

Cross-link the upstream kickoff procedure: concepts in `vendor/ultrathink-policy/kickoff-checklist.md` (desk copy of `ultrathink-kickoff` steps, with desk overrides). LEAD follows `skills/gotxcot-uplift` for the checklist. This document is the policy; the skill is the procedure.

### Notion — Agent Task Graph

| Item | Value |
|---|---|
| Collection | `be3418f0-d2d8-411b-8677-fa8a95ee63be` (`collection://…`) |
| Database | 🧩 Agent Task Graph |
| Hierarchy | **Task → Issue → Sub-Issue** (this database is the Kanban) |
| Idempotency | `Graph ID` (`ut-<base36>-<uuid8>`). Find-or-create Task. Issues by `Graph ID` + `nodeId`. Sub-Issues by `Graph ID` + `nodeId` + `step`. |

| Level | Role | Parent | Count |
|---|---|---|---|
| **Task** | One row per uplift run | — | 1 |
| **Issue** | One row per GoT node | Task | 5–8 |
| **Sub-Issue** | One row per CoT step | Issue | 4–8 per node |

Task fields (kickoff): `Item`, `Description`, `Uplifted Prompt` (≤~1900 chars; full XML stays in the session / second-uplift packet), **`Agent` = `cursor-cloud`**, `Status` (Planning → Implementing → …), `Linear State`, `Repo`, `Branch`, `Graph ID`, `Model`, `Started`, later `PR URL` / `PR #` / `PR State` / `Checks` / `Reviewers` / `Completed`.

- **Issue:** `Item` = `[nodeId] Title`, `Thought`, `Parent Item` → Task, `Graph ID`, `Linear URL`, `Issue ID`, `Issue Type` (Investigation / Feature from node kind).
- **Sub-Issue:** `Item` = `[nodeId] Step N: …`, `Step`, `Thought`, `Parent Item` → Issue, `Graph ID`, `Linear URL`.

Do not invent properties beyond the kickoff schema.

### Linear — Spectrum Web Co (dense)

| Kickoff step | Linear | Notion |
|---|---|---|
| Each node | **Issue:** title = node title, description = conclusion or question | Issue row; set `Linear URL` + `Issue ID` |
| Each CoT step | **Sub-issue** under that node’s issue: title `"{node title} — Step N: {snippet}"`, body = full step text | Sub-Issue under that Issue; set `Linear URL` |

Batch creates per node when possible. Report failed `nodeId` / `step` pairs. Do not stop after the first step.

### Compact (alternate only)

OMP `ultrathink-linear-got-cot`: one `[UT:…]` parent + one child per GoT node; CoT as short body text, not Linear rows. **Not** the desk default. Use only after `USAGE_LIMIT_EXCEEDED` (or an equivalent hard cap) and an explicit Lead decision recorded on the Task. Do not flip skills or this doc silently.

### Agent field

| Context | `Agent` value |
|---|---|
| Stock claude-ultrathink kickoff | `claude-code` |
| **Programming Desk (Cloud Agents execute)** | **`cursor-cloud`** |

If kickoff wrote `claude-code` and Lane A will run the work, set `cursor-cloud` before dispatch.

---

## Stage 6 — Second uplift (URLs inside the spec)

After every tracker row that will be dispatched has a URL (or an explicit failed-pair list):

1. Start from the **first-uplift XML**, already extended with graph conclusions if you have them.
2. Rewrite / extend it. Do not throw it away and write a short summary.
3. Inject one `<ISSUES>` element **inside the root** (a child of `BUILD_PROMPT` / `FIX_PROMPT` / …), not a markdown trailer.

```xml
<ISSUES>
  <TASK graphId="ut-…" notionUrl="https://www.notion.so/…">Task title</TASK>
  <ISSUE nodeId="n1" notionUrl="https://www.notion.so/…" linearId="SPE-…" linearUrl="https://linear.app/…">[n1] Title</ISSUE>
  <SUBISSUE nodeId="n1" step="1" notionUrl="https://www.notion.so/…" linearId="SPE-…" linearUrl="https://linear.app/…">[n1] Step 1: …</SUBISSUE>
  <!-- one ISSUE per node (5–8); one SUBISSUE per step (4–8 per node) -->
</ISSUES>
```

Rules:

- URLs are the ones just created. Do not invent Notion or Linear links.
- Every materialized Issue and Sub-Issue appears. Omitted steps are listed under a sibling `<TRACKER_GAPS>` with `nodeId` and `step`, not silently dropped.
- Keep ORIGINAL, SCOPE, ACCEPTANCE_CRITERIA, and the named surface sections. The second pass **adds** tracker identity, node conclusions, and step-level acceptance. It does not shrink the first pass.
- The final prompt is what dispatch sends. A work-packet header may precede it; the XML itself stays long.

Fold HITL answers (or stated defaults) into a `<CLARIFICATIONS>` child in the same pass. At most 4 blocking questions.

---

## Stage 7 — Dispatch

`skills/trackplan-dispatch` consumes the **second-uplift XML** (URLs included) plus the GitHub work packet.

| Lane | Runtime | When |
|---|---|---|
| **A** | Cursor Cloud Agent | Default. Notion `Agent` = `cursor-cloud`. |
| **B** | VPS Hermes | Ticket / runtime says `hermes`. Blocked while Hermes MCP auth/bridge is down — stop and record the blocker. |
| **C** | Specialist `SendToAgent` | Path ownership is already clear. Still attach the relevant issue/sub-issue URLs on the ticket. LEAD does not write the code. |

GitHub remains the source of truth for the change. Linear/Notion state alone is never “done”.

---

## Free-plan quota risk

Dense multiplies Linear rows: `nodes × (1 + steps)` plus the parent issues. Example: 5 nodes × 6 steps = 5 issues + 30 sub-issues. On a free-plan Spectrum Web Co workspace this can surface `USAGE_LIMIT_EXCEEDED`.

**Desk response without undoing Dense:**

1. Keep Dense as default.
2. Surface quota errors in the Lead receipt. Do not claim rows that were not created.
3. Escalate to Ove for a plan upgrade **or** an explicit one-run compact override. Not a silent policy flip.

---

## What this pack does not claim

| Item | Honest state |
|---|---|
| VPS engine patch | Documented in `vendor/ultrathink-policy/`. Not applied on the VPS from this repo. |
| Live Notion/Linear writes from this PR | Not run here. |
| Cloud Agent launch | Not run here. |
| Hermes | Auth/bridge blocked. No live handoff. |
| Greptile on a production PR | Policy stands. E2E not verified in this change. |
| PR → Notion/Linear sync skill | Still to build. Do not invent tracker rows at sync time. |

---

## References

| Path | Role |
|---|---|
| `skills/gotxcot-uplift/SKILL.md` | LEAD procedure: uplift → GoT → CoT → kickoff checklist → second uplift |
| `skills/trackplan-dispatch/SKILL.md` | Dispatch the second-uplift XML |
| `skills/trackplan-dispatch/prompt-template.md` | Packet scaffold |
| `vendor/ultrathink-policy/README.md` | Upstream constant and prompt diffs for the VPS copy |
| `docs/github-sot-orchestration.md` | GitHub SoT, lanes, Greptile, Hermes |
| `docs/desk-operating-model.md` | Tickets, channel, SendToAgent |
| `ownership.yaml` | Specialist 1:1 path ownership |
| `skills/greptile-merge-gate/SKILL.md` | QUALITY merge-claim Greptile enforcement |
