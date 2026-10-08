# Phase 1: Inventory and prove assumptions — Research

**Researched:** 2026-10-08  
**Domain:** Evidence-led Desk v2 kickoff, account/client inventory, prerequisite discovery and owned-path reconciliation  
**Confidence:** LOW under the installed research-provider classifier; authoritative local definitions and official documentation are identified separately below. This is complete planning research, not verified Phase 1 execution.

<user_constraints>
## User Constraints (from CONTEXT.md)

The following decisions, discretion and deferred-ideas text are copied verbatim. [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:17-32,81-83]

### Locked Decisions

### Evidence and phase gates
- **D-01:** Reuse the bounded, parent-observed inventory in `01-INVENTORY.md` and `01-INVENTORY.json`; preserve observed/configured/unverified distinctions. Actual service listeners and the railway-app identity are already evidenced. Do not infer private DNS, tailnet traversal, authenticated clients or mutation authority from them.
- **D-02:** Prove UUID access and prompt-file write/readback on an actual participating Bot, recording its exact path. A documented path or a value copied from the roster is not a live probe. Preserve existing prompt content and keep credential values out of artifacts; no guessed UUID or manufactured successful write.
- **D-03:** Observe the actual Grok Bot MCP client's `tools/list_changed` behavior, or select and exercise the documented connector fallback on observed non-support. Local server metadata alone is not proof of SaaS client capability. Offline `grok-bot-box`, absent mounted Bot tools and a failed browser relay are bounded access observations, not proof that the separate client is unsupported.
- **D-04:** Obtain actual authenticated Cursor team policy/tier and inventory the remaining prerequisite availability without exposing credential values. If access requires a human, return a blocking human-action checkpoint with the exact missing evidence; do not auto-approve, declare passed or start Phase 2.

### Source and ownership
- **D-05:** Kickoff retains the verbatim ORIGINAL in proposal §1, real traceable Notion Agent Task Graph/Linear Spectrum Web Co node and step links, and those live URLs in the second uplift. Preserve source scope; no fabricated tracker IDs/URLs, tickets, acknowledgements or second-uplift dispatch.
- **D-06:** `.planning/**` is LEAD-owned; `docs/upgrade-plan-desk-v2.md` is QUALITY-owned. Route the §13 source update through the appropriate owning slice and repository protocol. Preserve branch `bot-00-programming-lead/desk-swarm-subagents` and unrelated `web/desk3d/**`; do not silently edit a specialist path as LEAD or rewrite ownership to permit it. Companion agent-substrate has user changes and is not modified in this phase.

### User-resolved choices carried forward
- **D-07:** The user selected weekly Hindsight reflect, VPS plus Mac mini and XPS administrative access with exact mapped-port deny-default grants, and authorized human account-UI skill installation/activation. Seats remain proposal-only while `skills.approve` is absent. Record these now; actual scheduling/ACL/activation evidence belongs to the later phases and is not supplied by the design choice.
- **D-08:** Preserve locked D-1/D-2/D-3 and D-4's original-authoring-session scope. Independent QUALITY approval must bind the exact current reviewed SHA without creating a new tip; do not invent approvals or use on-branch stamp commits as approval. Continue only after actual phase verification; a human deferral is a resumable stop, not dependency clearance.

### Claude's Discretion

Use existing GSD artifact, ownership and receipt conventions and conservative read-only probes. Technical mechanics may be chosen from source/tool documentation; user decisions or inaccessible runtime evidence may not be guessed. No new capability or scope reduction is authorized.

### Deferred Ideas (OUT OF SCOPE)

None — no approved source scope was deferred. Downstream implementation remains assigned to its seven original phases, not discarded.
</user_constraints>

## Summary

Use an **inventory-and-human-evidence execution path**, not a gateway/network/data implementation plan. The approved boundary is “REQ-INVENTORY-001 through REQ-INVENTORY-016,” the full original kickoff and six n1 steps; it explicitly excludes forwarders, ACL changes, public-exposure retirement, data migration, template publication and downstream certification. The milestone remains “seven phases, 41 source steps and 217 retained requirements.” [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:8-10; .planning/ROADMAP.md:5,33-42]

The parent has already supplied useful bounded evidence: actual service listeners, production scopes and the Railway hostname identifying the existing tailnet node. Reuse those observations with their original observer and limitations. The remaining decisive evidence must come from an actual authenticated participating Bot, its MCP client, the actual Cursor team, credential owners, the running Hindsight API and GitHub/account control planes. The inventory calls its status “incomplete; acceptance unverified”; source/fixture existence is not a substitute. [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.md:3,7-41,47-56]

**Primary recommendation:** Materialize the complete source graph through the existing double-uplift/tracker protocol, collect only the bounded n1 observations, route §13 through a QUALITY-owned slice, and leave Phase 1 pending at explicit human checkpoints until the actual evidence and exact-current-SHA independent review exist. Do not clear a dependency on a deferral, an assumed client limitation or an approval stamp that changes the tip. [VERIFIED: skills/gotxcot-uplift/SKILL.md:148-194; .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:18-29]

## Architectural Responsibility Map

This is a responsibility recommendation derived from the source owners and boundaries, not a new deployment architecture. Source responsibility labels are “LEAD,” “INFRA,” “SYSTEMS in agent-substrate” and “LEAD → QUALITY docs ticket.” [VERIFIED: .planning/REQUIREMENTS.md:16-46; docs/upgrade-plan-desk-v2.md:316-328]

| Capability | Primary Tier | Secondary Tier | Responsibility and boundary |
|---|---|---|---|
| First uplift, graph identity, full tracker crosswalk, second uplift | LEAD orchestration/control plane | External Notion and Linear services | Preserve the original ask and actual tracker identities; do not dispatch downstream implementation merely because its rows exist. |
| Railway scopes, listeners, node identity and prerequisite metadata | Platform/INFRA | LEAD evidence record | Reuse parent observations; obtain owner confirmation of the account/project scope. No provisioning or ACL changes. |
| Own UUID and own prompt-file write/readback | Actual Bot client/computer | Authorized human account owner | Only that live client can prove its own identity and write result. The gateway renderer cannot prove a client filesystem write. |
| Actual list-change or pack-connector behavior | Actual SaaS MCP client | Existing gateway/SYSTEMS; human connector owner | Prove both the server/transport precondition and actual client result. No notification implementation or product API smoke in this phase. |
| Cursor tier, effective Bot network policy and event-trigger availability | External account/admin control plane | INFRA and LEAD | Authenticated account evidence, including effective group policy, belongs here; Cloud Agent settings are a different policy surface. |
| Mobile credential availability | INFRA/private credential boundary | Authorized Play/Apple account owners | Availability/ownership metadata only; no secret export, key generation or store-release action. |
| Hindsight version/model/dimensions | Running API/storage owner | SYSTEMS in agent-substrate | Establish actual prerequisites before the first Desk write; adapters, migration and compatibility acceptance remain n3. |
| Root CI registration/runner prerequisites | GitHub/platform control plane | INFRA workflow owner and QUALITY gate owner | A root workflow declaration is source evidence, not a live green run. No runner installation or gate changes here. |
| §13 reconciliation and independent review | QUALITY/repository governance | LEAD integration and human reviewer where required | Own paths and genuine receipts; approval must bind the reviewed tip without creating another commit. |

<phase_requirements>
## Phase Requirements — Full Phase 1 Crosswalk

**Descriptions below are verbatim requirement text**, not reduced acceptance criteria. IDs, source-step assignments and responsibilities are defined in the opened requirements block. All remain unchecked. “Now” means executable planning/source work, not a claim that this researcher performed the runtime action. [VERIFIED: .planning/REQUIREMENTS.md:9,15-46]

| ID | Description | Original source step / owner | Research support, execution path and required evidence |
|---|---|---|---|
| `REQ-INVENTORY-001` | Given the operator's original ask, when LEAD performs the first uplift, then ORIGINAL contains the verbatim §1 block, not a paraphrase. | Kickoff / LEAD | Copy the exact original in Code Examples; prepare full first-uplift XML using the existing skill. Parent later verifies the ORIGINAL text in the actual packet; an excerpt in this research is not a dispatched uplift. |
| `REQ-INVENTORY-002` | Given the selected full graph, when kickoff is recorded, then all seven nodes and their 41 source steps have traceable node issues and step sub-issues in the Notion Agent Task Graph and Linear Spectrum Web Co. | Kickoff / LEAD | Materialize every row in the 41-step crosswalk below. Fetch the actual collection schema, discover the actual Linear team, reuse a real graph identity and returned IDs, and retain the complete URL map. Account/schema/quota failures are checkpoints, not permission to compact the graph. |
| `REQ-INVENTORY-003` | Given created tracker rows, when the second uplift is dispatched, then its ISSUES section contains the live Notion/Linear URLs for the assigned node and steps. | Kickoff / LEAD | Extend the full first XML with ISSUES and CLARIFICATIONS inside the root. Verify real tracker results before dispatch; record the actual dispatch identity/result. Preserve all future-node links while only dispatching n1 work now. |
| `REQ-INVENTORY-004` | Given access to Ove's two Railway projects, when inventory is recorded, then actual service names, ports and environments are recorded for GreptimeDB, TimescaleDB, DragonflyDB, Hindsight and RAGFlow; provisional defaults are labelled until confirmed. | `n1.1` / LEAD → INFRA | Reuse the two production scopes, five service IDs and kernel-listener excerpts below. Confirm the relationship of the observed account to the authorized target projects. Keep private DNS targets and unobserved environments provisional; do not rerun failed listener/log attempts to confirm them. |
| `REQ-INVENTORY-005` | Given the railway-app tailnet node, when its identity is investigated, then its Railway project, role and advertised routes are recorded with evidence rather than inferred from online status. | `n1.2` / INFRA | Reuse the actual hostname-to-service proof and advertised routes. Record the bounded role as the observed subnet-route advertiser; obtain any still-needed owner/configuration evidence before deciding suitability as a forwarder. Adoption or retirement is later work, not n1 success. |
| `REQ-INVENTORY-006` | Given an actual Bot computer, when its UUID is read, then the receipt names the exact agent-data path and observed UUID. | `n1.3` / LEAD / participating Bot | Human opens the actual participating Bot and supplies a native computer/self-identity read trace. Corroborate which namespace belongs to that Bot before touching files. Exact observed path/UUID, client/account context and real output are necessary; roster values and fixtures are inadmissible substitutes. |
| `REQ-INVENTORY-007` | Given that Bot's own SYSTEM_PROMPT.xml, when write access is proved, then the result and exact writable path are recorded; a cited architecture path alone is not proof. | `n1.3` / LEAD / participating Bot | The same authorized Bot preserves its current bytes privately, actually writes the preserved bytes to its own actual prompt path, and reads back/computes equality evidence. Record write outcome/path and before/after evidence without copying prompt secrets into artifacts. Do not run full bootstrap, register seven seats or install a newly assembled prompt just to satisfy n1. |
| `REQ-INVENTORY-008` | Given Grok Bot's MCP client, when a pack changes the tools list, then observed notification support is recorded, or the fallback connector path is selected on observed non-support. | `n1.4` / LEAD / SYSTEMS | Actual authorized SaaS client trial, real task ID, baseline and changed discovery lists, negotiated protocol, evidence of an emitted/delivered notification and observed refresh result. On demonstrated non-support, human exercises the existing same-seat pack connector and records discovery/disable evidence. If notification delivery or the real public/authenticated connector is unavailable, keep the requirement pending; source tests and source-only fallback design do not pass it. |
| `REQ-INVENTORY-009` | Given the Cursor team's network settings, when inspected, then open versus Team-allowlist-only policy is recorded and the gateway allowlist need is identified. | `n1.5` / INFRA | Authenticated actual team/admin and effective group settings. Record the exact UI mode and allowed destination evidence; distinguish allow-all, defaults-plus-allowlist and allowlist-only instead of forcing four documented modes into a guessed binary. Identify the later gateway-entry need; do not change settings here. |
| `REQ-INVENTORY-010` | Given the team's plan, when inventoried, then its tier is recorded without assuming Enterprise Team Setup is available. | `n1.5` / LEAD | Actual team billing/plan evidence with account/team identity. Public Enterprise-only documentation is a product constraint, not the observed tier. Relay timeout or a missing panel without authenticated tier evidence cannot establish non-support. |
| `REQ-INVENTORY-011` | Given n1 findings, when the plan's assumptions are updated, then §13 distinguishes observed results, unresolved assumptions and unexercised behavior with source evidence. | `n1.6` / LEAD → QUALITY docs ticket | Real QUALITY ticket/links; QUALITY-owned source update with the reconciliation checklist below; actual independently reviewed result and receipt. A LEAD note saying “route later” alone does not deliver this requirement. Preserve pending items and D-4's original-session provenance. |
| `REQ-INVENTORY-012` | Given the mobile release integrations, when credentials are inventoried, then availability and ownership of Play Developer and App Store Connect credentials are recorded without disclosing their values to Bots or templates. | `n4.3` prerequisite / INFRA | Owner-attested/account-backed availability, app/account scope, custody and access/readability metadata only. Known absence can be a truthful inventory result, but blocks the later integration; unknown/access-denied is not verified absence. No release, key creation or “status” call that creates a Play edit. |
| `REQ-INVENTORY-013` | Given Railway Hindsight, when preparing to store data, then its actual version and embedding dimensions are established before the first stored data; the cited template version is not asserted as the live version. | `n3.2` prerequisite / SYSTEMS in agent-substrate | Running API version evidence and actual effective embedding provider/model/dimensions, tied to the identified service/deployment. Image tag and public health remain separate facts. Obtain owner-provided read-only runtime/config/schema evidence; no guessed version endpoint, retain call, upgrade, vector reset or compatibility acceptance here. |
| `REQ-INVENTORY-014` | Given the PR gate workflow, when CI activation is claimed, then an active root .github/workflows/gates.yml is evidenced rather than inferred from ci/.github/workflows/gates.yml or the historical inventory. | `n5.1` prerequisite / INFRA / QUALITY | Root source was opened and is present; correct §13's obsolete absence assertion. For an activation claim, obtain actual remote workflow/run, event, SHA, Actions and runner availability evidence. Keep “declared root workflow” distinct from “active/current successful CI.” Activation fixes remain n5.1. |
| `REQ-INVENTORY-015` | Given the team's Cursor integrations, when intake event triggers are evaluated, then their actual availability is recorded and the ten-minute polling floor remains when triggers are unavailable. | `n6.3` prerequisite / LEAD | Inspect authenticated Cursor account-integration/routine controls, not just a GitHub plugin or the intake YAML. Capture actual availability or verified unavailability. Retain the documented ten-minute fallback; do not enable routines or execute a Test Run as inventory. |
| `REQ-INVENTORY-016` | Given a new Desk v2 path, when work is assigned, then ownership already covers it with last-match-wins resolution and declared contract consumers; an unowned path fails G-1. | `n1` / before `n4–n5` path creation / QUALITY | Resolve planned paths against the actual ordered manifest, including narrow/later overrides and contract consumers. Existing rules are reusable; no new product paths are needed by n1. Route any uncovered future path to QUALITY before creation. Parent verifies G-1 after owned slices land; no ownership rewrite to allow a foreign edit. |
</phase_requirements>

## Standard Stack

### Core — Reuse, Do Not Install or Replace

The existing gateway declares `name = "desk-gateway"`, `version = "0.1.0"`, `requires-python = ">=3.11"`, and dependencies `"httpx>=0.28.1"`, `"mcp[cli]>=2.2.0,<3"`, `"pydantic>=2.11"`, `"pyjwt[crypto]>=2.8"`, `"pyyaml>=6.0"`, `"uvicorn>=0.34"`. These are **opened source declarations**, not registry legitimacy verdicts, installed-version observations or Phase 1 installation recommendations. [VERIFIED: services/desk-gateway/pyproject.toml:1-18]

| Existing mechanism | Version / evidence boundary | Use in this phase |
|---|---|---|
| Repository GSD artifacts and current config | `"nyquist_validation": true`, `"security_enforcement": true`, `"security_asvs_level": 1`, `"auto_advance": false`, `"branching_strategy": "none"`, `"skip_checkpoints": false` | Preserve manual stops and the existing branch; plan evidence capture rather than add application code. [VERIFIED: .planning/config.json:4-12,34-43] |
| Existing Python MCP gateway | Source-declared constraints above; actual negotiated client/server versions unobserved | Inspect/reuse per-seat and pack discovery surfaces; do not replace this with a new web stack. [VERIFIED: services/desk-gateway/src/desk_gateway/server.py:81-105,367-370] |
| Actual Grok Bot account/computer and client | Public product docs, not observed client capability | Required for the UUID, file-write and discovery observations. The account computer and installed connectors are shared across Bots; separate screens are not security boundaries. [CITED: https://docs.x.ai/grok-bot/computer-and-apps] |
| Mounted Notion and Linear tools | Schemas inspected; account permissions/schema/quota not exercised | Execute existing graph materialization later with actual returned IDs and URLs. [CITED: xd://mcp__notion_fetch; xd://mcp__notion_create_pages; xd://mcp__linear_list_teams; xd://mcp__linear_list_issues; xd://mcp__linear_save_issue] |
| Existing ordered ownership and receipt protocols | `"docs/**"`, `".planning/**"`; own receipt pattern `".receipts/<bot-id>/<task-id>.json"` | Specialist routing and truthful evidence; the receipt pattern is a protocol target, not a claim that a receipt was created. [VERIFIED: ownership.yaml:239-240,401-402; skills/verification-receipts/SKILL.md:60-63] |

### Supporting

Use the existing gate/test infrastructure rather than introduce a framework. Source imports `pytest`, the gateway dev group declares `"pytest>=8.0"`, and root CI declares `python-version: "3.12"` and `pip install pyyaml pytest`. Actual local installed versions were not probed. [VERIFIED: ci/tests/test_gates.py:26; services/desk-gateway/pyproject.toml:32-41; .github/workflows/gates.yml:223-228]

**Installation:** None in Phase 1 research or the recommended inventory slice. Registry versions/publish dates and package legitimacy were not queried because no new dependency is proposed. Do not convert these existing source constraints into a dependency bump or an install task.

### Alternatives Rejected by the Locked Scope

- A new gateway, a fixture-based client test, or a different networking topology would not answer the live inventory question. Preserve D-2: “Bots reach Railway through a **Desk Gateway on the VPS**, not by joining the tailnet.” [VERIFIED: docs/upgrade-plan-desk-v2.md:48]
- Do not replace the fixed graph with a compact/partial tracker graph. Its approved count is “seven phases, 41 source steps and 217 retained requirements.” [VERIFIED: .planning/ROADMAP.md:5]
- Do not replace human UI activation with an invented approval tool. The choice is “Authorized human operator”; actual activation/publication remains a later gate. [VERIFIED: .planning/INGEST-CONFLICTS.md:26-28]

## Architecture Patterns

### System Architecture Diagram

Recommended execution flow, grounded in the double-uplift, n1 and independent-review protocols. The diagram shows processing and stop/resume decisions, not a proposed service build. [VERIFIED: docs/upgrade-plan-desk-v2.md:314-330; docs/desk-operating-model.md:138-147,202-240; .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:18-29]

```text
Operator's exact original ask + locked decisions
                 |
                 v
Full first uplift + fixed seven-node/41-step graph
                 |
                 v
Authenticated Notion / Linear lookup and materialization
        | missing permission/schema/quota
        +---------------------------------> Blocking owner/human action
        | actual complete URL map                     |
        v                                             | resume with evidence
Full second uplift, actual n1 dispatch <---------------+
                 |
                 v
Owned n1 tickets / prerequisite inventory
        |                        |
        v                        v
Reuse parent observations    Actual Bot/client/account/owner evidence
        |                        | inaccessible or unexercised
        |                        +----------> Blocking human checkpoint
        +------------------------+                    |
                 |                                    | resume
                 v <----------------------------------+
QUALITY-owned §13 reconciliation; separate owner receipt/review
                 |
                 v
Main's consolidated checks + independent review of exact current SHA
        | missing evidence, approval, or gate clearance
        +---------------------------------> Pending; no Phase 2 clearance
        | genuinely verified
        v
Phase 2 dependency clears; only documented gateway-skeleton overlap allowed
```

### Recommended Artifact Structure — Existing Paths Only

The context names `"01-NN-PLAN.md"` for future plans and says summaries are written “only after actual plan completion.” Durable inputs are `"01-INVENTORY.md"`, `"01-INVENTORY.json"` and the implementation map. Do not create a second evidence convention or mark an unexecuted plan summarized. [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:39-51,66; .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.json:24-30]

| Source / artifact | Responsibility and reuse |
|---|---|
| Phase context, requirements and roadmap | Locked decisions and acceptance/source-step identities; parent owns progression. |
| Existing phase inventory Markdown/JSON | Preserve original observer, exact command supplement, configured versus observed facts and disclosed omissions. |
| Existing implementation map | Bounded authored-capability reconciliation, not current deployed acceptance or the exact companion snapshot. |
| Existing proposal §13 | QUALITY-owned source reconciliation, not a LEAD scratch document. |
| Existing own-seat receipt convention | Record actual parent/specialist commands, result evidence, manual evidence references and every unverified boundary. Never manufacture command exits for UI actions or copy an old receipt as this task's receipt. |

Sources for these responsibilities: “parent-observed,” “incomplete_unverified,” “Individual probe timestamps were not captured,” and “one concrete ticket per owning seat.” [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.json:5-21,32-39; docs/desk-operating-model.md:138-147; .github/workflows/gates.yml:108-153]

### Pattern 1: Evidence Has a Subject, Observer and Boundary

**Use now:** Reconcile the existing record without repeating its probes. Its source labels the observer `"parent"` and distinguishes `"Configured port, observed container listener, public health, tailnet traversal and authenticated client acceptance"`. Preserve those subjects; a claim about one must not become a claim about another. [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.json:7-21]

**Recommendation:** Each new observation should identify the requirement/source step, actual account/client/service, observer, genuine acquisition action/result, capture time when available, source attachment/path and remaining limitation. Keep missing historical timestamps missing. For manual UI evidence retain genuine screenshots/transcripts and independent interpretation; do not invent a shell command or exit code to make a receipt look automated. Existing receipt fields are `"commands"`, `"claims"`, `"evidence_command_index"` and `"unverified"`; only actual exercised commands belong in that command record. [VERIFIED: skills/verification-receipts/SKILL.md:60-88,207-216]

### Pattern 2: Re-entrant Kickoff, Non-Re-entrant Dispatch

The source graph key is `"ut-<base36>-<uuid8>"`; re-entry updates the Task rather than duplicating it. Dispatch separately checks for an existing launch; inability to list launches is recorded as unverified, not “none exist.” [VERIFIED: vendor/ultrathink-policy/kickoff-checklist.md:24,35-37; skills/trackplan-dispatch/SKILL.md:195-204]

Recommended sequence:

1. Preserve §1 text exactly, including its original spelling. Fill the first uplift's actual required operational sections, not a skeletal XML template. The skill's roots include `"BUILD_PROMPT"` and its required children include `"ORIGINAL"`, `"SYSTEM_ROLE"`, `"CONTEXT"` or `"APP_CONTEXT"`, `"SCOPE"`, `"CONSTRAINTS"`, `"ACCEPTANCE_CRITERIA"`, `"OUT_OF_SCOPE"`. [VERIFIED: skills/gotxcot-uplift/SKILL.md:46-62]
2. Recover an existing graph identity if already materialized; otherwise generate it once during actual kickoff. Search Notion content through its search tool and query the fetched data source by the actual Graph ID; paginate Linear lookup and retain real parents/children. The configured destination is `"collection://be3418f0-d2d8-411b-8677-fa8a95ee63be"`, named Agent Task Graph, and the named Linear team is “Spectrum Web Co.” These are source-configured destinations, not verified writable resources in this research. [VERIFIED: vendor/ultrathink-policy/kickoff-checklist.md:35-37,54-68; CITED: xd://mcp__notion_search; xd://mcp__notion_query_data_sources; xd://mcp__linear_list_teams; xd://mcp__linear_list_issues]
3. Fetch the actual Notion destination first and read its current property schema. The creation tool uses `parent.data_source_id` for a collection; page relationships are arrays of actual page IDs/URLs in properties. Task/Issue/Sub-Issue rows share the collection; `"Parent Item"` is the relation, not a request to nest child pages under an Issue page outside the database. Fetch the Notion Markdown specification through Notion before future content writes. [CITED: xd://mcp__notion_fetch; xd://mcp__notion_create_pages; VERIFIED: vendor/ultrathink-policy/kickoff-checklist.md:41-68]
4. Create/update one Task, seven node Issues and 41 step Sub-Issues in Notion; seven parent issues and 41 child issues in Linear. Expected totals are therefore **49 Notion rows** and **48 Linear issues**, derived from the source's one Task plus one Issue per node and one Sub-Issue per step. Source count quote: “seven phases, 41 source steps and 217 retained requirements.” No row or identifier is claimed created here. [VERIFIED: .planning/ROADMAP.md:5; vendor/ultrathink-policy/kickoff-checklist.md:33-68]
5. Use actual returned Linear IDs for `parentId`, node dependency links and updates. A created child must belong to its actual node parent. Discover actual status/assignee values instead of translating seat labels into guessed account IDs. Notion's source property values include `"Level" = "Task"`, `"Status" = "Planning"` until dispatch, `"Linear State" = "Todo"`; `"Agent" = "cursor-cloud"` only when Lane A will execute. Reconcile these with the fetched live schema rather than assume all options exist. [VERIFIED: vendor/ultrathink-policy/kickoff-checklist.md:41-68; CITED: xd://mcp__linear_save_issue; xd://mcp__notion_create_pages]
6. For asynchronous Notion creation, wait for an actual succeeded result before depending on its pages; do not use an async task ID as a page URL. Preserve partial successes, failure pairs and IDs for resumption. The source explicitly handles `"USAGE_LIMIT_EXCEEDED"` by stopping/escalating; it does not authorize automatic compact mode. This approved full graph does not permit tracker-less or compact execution without a new explicit scope decision. [CITED: xd://mcp__notion_create_pages; xd://mcp__notion_get_async_task; VERIFIED: skills/gotxcot-uplift/SKILL.md:152-159; .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:24,32]
7. Extend the full first XML with `"ISSUES"` and `"CLARIFICATIONS"` **inside the root** and actual Task/node/step URLs. Record genuine gaps without treating them as acceptance. Set the Task to `"Implementing"` only when actual dispatch is imminent. The full source graph is tracking scope; only n1 is currently execution scope. Hosted dispatch here is omp, not a claimed signed AgentSwarm bus or proof that a source-described SendToAgent/Cloud Agent call occurred. [VERIFIED: skills/gotxcot-uplift/SKILL.md:163-194; vendor/ultrathink-policy/kickoff-checklist.md:78-90; .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:10,66]

### Pattern 3: Reuse the Actual Railway Inventory, Not Defaults

The parent inventory's two opened scopes are “Ultrathink” / production and “Agent Substrate” / production. Account display values are “Ming Chen” and “Ming Chen's Projects”; the record expressly does not establish that identity as Ove's. Confirm authorized target scope before mutation or declaring it the operator's account. Other environments/ancillary service IDs were not supplied. [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.md:7-12,23-28,47; .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.json:45-52]

| Parent-observed scope / service | Verbatim IDs / listener values from the durable record | Reuse and limitation |
|---|---|---|
| Ultrathink production | Project `67a98752-ba0a-4ae2-a881-8d0e33a89328`; environment `6cfcb6de-3175-418b-8e20-7817a3d31633` | Confirmed observed scope, not inferred account ownership. |
| Agent Substrate production | Project `a3453be1-819a-4ac3-a787-c6cfa5550f18`; environment `c50e0706-deb0-43ad-aaa0-53a92da3b396` | Same boundary. |
| GreptimeDB | Service `b53b4c7d-df3c-4cd8-a15d-e5fb1a79e254`; `4000/4001/4002/4003` | Only `4000/4001/4003` are approved forwarder mappings; extra listener 4002 does not widen the ACL. |
| TimescaleDB | Service `1bd7a6fd-b7b2-4fe4-8b4f-0d76ead81d79`; `5432` | Container listener observed; public proxy remains. |
| Dragonfly | Service `32ee49a2-61bb-4572-acc8-1aa5956b6c7f`; `6379` | Kernel listener proof succeeds independently of the failed ss attempt. |
| hindsight-api | Service `0436123d-6fff-4bd8-a9a5-bd38db9ffff1`; `8888`; configured image `ghcr.io/vectorize-io/hindsight-api:0.9.1` | Image is configuration, not server-reported version/model/dimensions. |
| ragflow | Service `8ddda0d9-44d4-4e7a-8eec-6dbf91bb8d9e`; `9380/9382/80` | Only API 9380 and explicitly optional web 80 are mapped; 9382 does not become authorized. |
| tailscale-vpn / railway-app | Service `fcb79134-ca20-4816-8c10-ffaf18da5d7f`; actual hostname output `railway-app` | Matched to Ultrathink production, not a verified replacement forwarder. |

All ID/listener/image cells above quote the opened inventory, not live calls by this researcher. [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.md:11-21]

The actual six SSH invocations and exit/result excerpts are already stored under `"parent_command_supplement"` at JSON lines 32–39. Reuse that exact protocol record instead of reconstructing commands or rerunning failed log/ss checks. The matched node is `"100.77.7.42"`, with routes `"10.128.0.0/9"`, `"fd12:4f8:a4d6:1::/64"`, `"fd12::10/128"` and role `"observed subnet-route advertiser, not a verified per-project forwarder"`. Project identity, route advertisement, forwarding functionality and retirement authorization are distinct. [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.json:32-39,149-162]

Do not replace documented private DNS/mapping targets with a claim of resolved DNS or successful traversal. The inventory says listeners are “inside those containers” and do not prove “private DNS resolution, TCP traversal, authenticated APIs, per-client authorization or cutover.” [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.md:28]

### Pattern 4: Actual Self-UUID and Byte-Preserving Prompt Write

The repository documents runtime loading of `"SYSTEM_PROMPT.xml"` under `"/home/box/agent-data/agents/<uuid>/"`. The gateway returns the literal `"install_path_hint": "/home/box/agent-data/agents/<your-uuid>/SYSTEM_PROMPT.xml"`; these are **documented targets/hints**, not evidence that this client's directory exists or is writable. No script creating the actual Bot path or actual observed self-UUID was supplied. [VERIFIED: ARCHITECTURE.md:198-201; services/desk-gateway/src/desk_gateway/tools/core.py:212-225]

The current doctor registration consumes a caller-supplied `"agent_uuid"`; prompt installation renders text and stores an expected hash. Its prompt check compares caller-supplied `"prompt_sha256"` against the expected hash, and skill checking consumes caller-supplied `"installed_skills"`. None of those operations reads or writes the remote Bot's prompt file. Do not treat a fixture UUID, rendered prompt, expected hash or doctor response as n1 filesystem proof. [VERIFIED: services/desk-gateway/src/desk_gateway/tools/core.py:203-240]

**Recommended actual execution boundary:**

1. Authorized human opens the actual participating Bot and its Agent Computer; authenticate or take over sensitive steps in the UI, not by pasting credentials into chat. Public docs describe command-line/file access but do not establish this Bot's self-UUID interface. Discover the actual native tools/self-identity evidence available there; do not invent a hosted read/write API. [CITED: https://docs.x.ai/grok-bot/computer-and-apps]
2. Read/corroborate that selected Bot's own UUID and exact directory/file path before any write. The shared account computer contains files visible to every Bot, so “a directory exists” alone does not identify the current Bot. Stop if identity-to-namespace binding is unclear. [CITED: https://docs.x.ai/grok-bot/computer-and-apps; VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:19]
3. Preserve existing prompt bytes privately, actually write those preserved bytes to the same actual file, then read back and establish equality with real output. Retain bounded hashes/results and the actual path/UUID required by the acceptance criterion, not prompt contents, tokens or someone else's files. If the file is absent or access fails, preserve the failure and obtain owner action; do not manufacture a prompt or writable-path success. [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:19; .planning/REQUIREMENTS.md:25-28]
4. This narrow write proof is not n5 bootstrap/registration/prompt installation. Keep actual group/roster setup, shared-library activation and full doctors at their later boundaries. [VERIFIED: .planning/ROADMAP.md:129-133; .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:10,28]

### Pattern 5: Separate Server Notification Delivery from Client Support

Repository shorthand is `"tools/list_changed"`; the wire method is `"notifications/tools/list_changed"`. The 2025-11-25 tools specification describes `"listChanged": true` and the server notification. The 2026-07-28 specification additionally describes a `subscriptions/listen` stream with `toolsListChanged: true`. Record the **actually negotiated protocol**, server/client versions and transport; do not silently migrate the existing deployment to the newest specification. [VERIFIED: docs/upgrade-plan-desk-v2.md:180-190,340; CITED: https://modelcontextprotocol.io/specification/2025-11-25/server/tools; https://modelcontextprotocol.io/specification/2026-07-28/server/tools]

The opened source currently:

- Computes discovery from the seat roster plus stored loaded packs; a direct pack route returns that pack's surface. [VERIFIED: services/desk-gateway/src/desk_gateway/server.py:81-105]
- Builds MCP HTTP with `streamable_http_path="/mcp", json_response=True, stateless_http=True`. These settings are source facts, not proof of live notification delivery or incompatibility. [VERIFIED: services/desk-gateway/src/desk_gateway/server.py:367-370]
- Updates pack state and returns `"the pack's tools appear on the next tools/list; if Grok Bot does not refresh, enable the pack connector at /mcp/<seat>/packs/<app>"`. No notification send appears in the opened `app_tools_load` function. This exposes an **emission precondition to establish**, not a finding that the SaaS client or the complete SDK cannot support notifications. [VERIFIED: services/desk-gateway/src/desk_gateway/tools/packs.py:17-39]
- Has documentation asserting “After a load the gateway emits MCP `notifications/tools/list_changed`.” That documented expectation must be checked against actual delivery; it cannot override the bounded code observation or become a client pass. [VERIFIED: skills/tool-packs/SKILL.md:78-90]

**Recommended bounded trial for Main/authorized runtime owner, not this researcher:**

1. Use the actual authenticated SaaS Bot with an available authorized same-seat connector and a real n1 task identity. The source says load is on ANDROID/IOS rosters; WEB uses fallback directly. Use an already declared initial pack: `"kanbanos"`, `"desklanes"` or `"clippyos"`, not later additional packs as a scope substitution. [VERIFIED: skills/tool-packs/SKILL.md:14-22; docs/upgrade-plan-desk-v2.md:180-190]
2. Capture initial tool discovery/count, actual negotiated protocol/capability and the transport needed to receive its notification. Load only for the real ticket; do not call product smoke, push, SQL or release tools. Obtain evidence of server emission/delivery and then actual client rediscovery. A fresh manual tools/list proves server discovery changed, not automatic client notification handling. [CITED: https://modelcontextprotocol.io/specification/2025-11-25/server/tools; https://modelcontextprotocol.io/specification/2026-07-28/server/tools; VERIFIED: services/desk-gateway/src/desk_gateway/tools/packs.py:17-39]
3. If non-refresh is observed after valid notification delivery, record that bounded non-support and use the documented connector-refresh/fallback sequence. If delivery, public reachability, authentication or account control is unavailable, state the exact missing precondition and stop; neither an offline peer nor an undelivered notification proves client non-support. [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:20; skills/tool-packs/SKILL.md:78-90]
4. Fallback URL is the documented `"https://desk.swcstudio.space/mcp/<seat>/packs/<app>"`, with the same seat authorization, enabled by the human in “Marketplace → Your plugins” for the ticket and disabled afterward. The runtime route definition is opened below in Code Examples. Capture real fallback discovery and aggregate exposure across connectors; do not assume source-local ceilings prove account-wide exposure. Keep the intended `"Live tools per seat never exceed 20"` and at most five tools per pack. [VERIFIED: skills/tool-packs/SKILL.md:12-22,83-90; services/desk-gateway/src/desk_gateway/server.py:46,81-88]
5. Record actual unload/disable results without asserting cleanup ran in this research. Public docs say installed connectors are account-wide: use a human-approved participating account and avoid changing other Bots' active surfaces. A scoped connector-discovery trial is not evidence of n5 shared-library/plugin activation or publication. [CITED: https://docs.x.ai/grok-bot/computer-and-apps; VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:28; skills/tool-packs/SKILL.md:14-16,87-90]

The parent observed gateway `"registered_seats": []`, `"channel_registered": false` and public reader `"failed DNS ETIMEOUT"`; these are unmet access preconditions, not invitations to implement gateway/public-network fixes inside n1. [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.json:171-190]

### Pattern 6: Authenticated Account Inventory, Not Feature Inference

**Cursor:** Official docs affirmatively state Team Setup and Network Controls are Enterprise-only. The documented modes are “No Policy (Allow All),” “Allow All Network Access,” “Defaults + Team Allowlist,” and “Team Allowlist Only.” Groups may replace the team policy, and the Grok Bot policy is separate from Cloud Agent network settings. [CITED: https://docs.x.ai/grok-bot/private-networks; https://docs.x.ai/grok-bot/security]

Recommendation: Have the actual authorized admin/account owner capture the actual team identity/tier and effective Bot/group policy from the Cursor dashboard, using the documented Grok Bot page `https://cursor.com/dashboard/bot`. Record the actual label and destination evidence, including whether the gateway host needs an entry. Do not infer tier from a failed login/missing panel or assume defaults without authenticated team evidence. An allowlist addition belongs to `n4.5`; no Team Setup manifest, Bot Tailscale installation or desktop-egress toggle is part of n1. [CITED: https://docs.x.ai/grok-bot/security; VERIFIED: .planning/REQUIREMENTS.md:31-34,82-85; docs/upgrade-plan-desk-v2.md:48]

**Triggers:** Cursor account integrations can start routines from GitHub/Slack events and are distinct from the corresponding plugins. Inspect actual event-control availability and connection status without enabling a routine or running its task. The retained floor is “the 10-minute poll”; missing or unobserved triggers do not justify removing it. Actual intake trigger exercise/acknowledgement remains `n6.3`. [CITED: https://docs.x.ai/grok-bot/skills-routines-and-automations; VERIFIED: docs/upgrade-plan-desk-v2.md:347; .planning/ROADMAP.md:173]

### Pattern 7: Inventory Mobile Credentials Without Using Them

Opened readers consume `PLAY_ACCESS_TOKEN`, `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_PRIVATE_KEY_PATH`. The documented long-term platform-token home is `"/etc/desk-gateway/gateway.env"`; data-plane credentials belong to `"/etc/substrate/substrate.env"`. These are source-described custody targets, not observed runtime files or permissions. Do not dump environment values or use a rendered-variable listing as the inventory record. [VERIFIED: services/desk-gateway/src/desk_gateway/config.py:169-172; infra/substrate/SUBSTRATE-ENV.md:25-31]

Recommendation: INFRA and the actual account owners report availability, owner/custodian, authorized app/account scope, expiry/rotation responsibility and presence/readability metadata, with values withheld. Google documents Play API enablement and appropriate Console permissions; Apple documents Account Holder API-access requests and Account Holder/Admin team-key management. Inspect existing availability only—do not request access, generate/rotate/download keys or provision a service account in this slice. [CITED: https://developers.google.com/android-publisher/getting_started; https://developer.apple.com/help/app-store-connect/get-started/app-store-connect-api/]

**Important side effect:** `play_track_status` calls `play.edit(...)` before reading a track; `PlayConsole.edit` issues `"POST"` to `"/applications/{package_name}/edits"`. It is not a safe credential-presence probe merely because its name sounds read-only. [VERIFIED: services/desk-gateway/src/desk_gateway/tools/mobile.py:18-29; services/desk-gateway/src/desk_gateway/upstreams.py:538-557]

A verified unavailable credential with its owner identified can satisfy honest availability inventory; it does **not** clear n4's actual mobile tool/release prerequisite. An access error establishes neither presence nor absence. No credential value goes to a Bot, template, tracker or receipt. [VERIFIED: .planning/REQUIREMENTS.md:37-38; .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:21,28]

### Pattern 8: Hindsight Prerequisites Before Any First Desk Write

The proposal's exact assumption is `"v0.10.1-slim"`; the parent observed configured image `"ghcr.io/vectorize-io/hindsight-api:0.9.1"`. The parent health body reports `"status":"healthy"` and `"database":"connected"`; no live version, model or dimensions were established by that observation. This is not a verified compatibility failure or a reason to mandate an upgrade. [VERIFIED: docs/upgrade-plan-desk-v2.md:346; .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.md:20,36]

Official Hindsight documentation provides versioned documentation and describes embedding configuration/dimensions. Its current configuration guidance warns that dimension changes after storage are destructive and that equal dimensions from different models do not imply comparable embeddings. This explains the prerequisite; it does **not** supply this instance's configuration or certify the documented newer behavior on the observed image. [CITED: https://hindsight.vectorize.io/0.9; https://hindsight.vectorize.io/developer/configuration#embedding-dimensions; https://hindsight.vectorize.io/developer/configuration#embeddings]

Recommendation: SYSTEMS/runtime owner supplies read-only evidence of the running **API service** version and actual effective provider/model/dimensions, correlated to that service/deployment, plus whether existing data already fixes an embedding space. Use the deployment's existing supported metadata, startup/configuration output or owner-observed installed-version/schema evidence; discover the supported mechanism for the actual version rather than invent `/version` or assert that `/health` must contain a version field. Exclude credentials from the captured configuration. No retain/recall acceptance call, vector alteration, migration, upgrade, memory-config retirement or bank seeding is performed here. [VERIFIED: .planning/REQUIREMENTS.md:39-40; docs/upgrade-plan-desk-v2.md:320,346; services/desk-gateway/src/desk_gateway/upstreams.py:336-356]

Preserve the user-selected **weekly** reflect choice now; implementing/exercising it, authorized `"pd-*"` banks, backed-up local-memory retirement and adapter compatibility belong to n3. The companion source map did not capture the exact inspected revision; the later dirty-HEAD observation is not that earlier snapshot. Re-establish applicability with the companion owner before Phase 3; do not modify/fetch/reset that checkout in n1. [VERIFIED: .planning/INGEST-CONFLICTS.md:18-20; docs/upgrade-plan-desk-v2.md:320; .planning/intel/implementation-map.md:5,29-31]

### Pattern 9: Correct Root CI History Without Claiming Activation

The opened root workflow declares `name: Quality Gates`, PR/push branches `[main]`, a PR-only `gates` job and `runs-on: [self-hosted, Linux, X64]`. It also overlays gate scripts from the PR base before executing them. Root source existence disproves §13's old root-absence statement, but not an unavailable runner, disabled Actions or an unexecuted PR gate. [VERIFIED: .github/workflows/gates.yml:23-60; docs/upgrade-plan-desk-v2.md:344]

GitHub requires workflow files in the repository's root `.github/workflows` directory. The nested gate template is not a live workflow merely by existing. [CITED: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax]

Recommendation: Inventory actual remote Actions/workflow registration, applicable event/branch/SHA, permitted runner availability and existing run URLs before making an activation claim. Do not install runners, change billing, dispatch/rerun CI or weaken the trusted-base overlay in this research. Main alone runs authorized consolidated verification after all workers land. Activation work remains `n5.1`. [VERIFIED: .planning/REQUIREMENTS.md:41-42; .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:66; .github/workflows/gates.yml:46-60,203-228]

The intake workflow separately declares `issues: types: [labeled]`, label `"desk:intake"`, `runs-on: ubuntu-latest` and secret `"DESK_INTAKE_TOKEN"`. Source presence does not prove the GitHub secret/hosted runner/public endpoint is available, nor prove Cursor routine triggers. Do not send an intake POST or label an issue as an inventory shortcut. [VERIFIED: .github/workflows/desk-intake.yml:1-21; .planning/ROADMAP.md:159,173]

### Pattern 10: Cross-owner §13 Delivery, Not Foreign Edits

The actual resolver says `"Last matching rule wins."` It assigns the last matched owner/contract flag; unowned/foreign paths fail. This is the executable convention, not a first-match reading of comments. [VERIFIED: ci/gates/check_ownership.py:62-72,143-163]

| Verbatim rule/path | Verbatim owner / consumers | Required routing |
|---|---|---|
| `.planning/**` | `bot-00-programming-lead` | LEAD planning/evidence slice; parent progression/commits. [VERIFIED: ownership.yaml:401-402] |
| `docs/upgrade-plan-desk-v2.md`, covered by `docs/**` | `bot-06-quality-security` | QUALITY owns §13; real n1.6 ticket and independently reviewed owned slice. [VERIFIED: docs/upgrade-plan-desk-v2.md:298; ownership.yaml:239-240] |
| `.github/workflows/**` | `bot-05-infrastructure` | General root CI changes belong to INFRA, not LEAD. [VERIFIED: ownership.yaml:164-165] |
| `.github/workflows/security-*.yml` | `bot-06-quality-security` | Narrow security override; do not route all workflows by the broad rule alone. [VERIFIED: ownership.yaml:173-174] |
| `ci/.github/workflows/**`, then later `ci/.github/**` | Earlier `bot-05-infrastructure`; later winning `bot-06-quality-security` | Current effective nested template owner is QUALITY, despite the earlier comment. Future root/template changes need both owners; n1 does not rewrite ownership. [VERIFIED: ownership.yaml:182-183,370-371; ci/gates/check_ownership.py:62-72] |
| `services/desk-gateway/**` | `bot-01-systems-backend` | Source research only in n1; implementation remains its downstream slice. [VERIFIED: ownership.yaml:347-348] |
| `infra/desk-gateway/**`, `infra/railway/**`, `infra/tailscale/**` | `bot-05-infrastructure` | INFRA downstream work, not inventory implementation. [VERIFIED: ownership.yaml:349-354] |
| `contracts/tool-rosters/**` | `bot-06-quality-security`; `contract_surface: true`; consumers `bot-00-programming-lead`, `bot-01-systems-backend`, `bot-02-web-edge`, `bot-03-android`, `bot-04-ios`, `bot-05-infrastructure`, `bot-06-quality-security` | Retain real contract-first consumer acknowledgements before later implementation. [VERIFIED: ownership.yaml:355-357,436-443] |
| `contracts/tool-packs/**` | `bot-06-quality-security`; `contract_surface: true`; consumers `bot-02-web-edge`, `bot-03-android`, `bot-04-ios` | Same; source lists do not constitute acknowledgements. [VERIFIED: ownership.yaml:358-360,444-447] |

**Executable owned-slice strategy:**

1. LEAD prepares the bounded §13 evidence packet in its own planning slice, with real n1.6 node/step tracker links. The ticket includes the source protocol's fields `"task_id"`, `"owner"`, `"goal"`, `"paths_in_scope"`, `"out_of_scope"`, `"trackers"`, `"success_criteria"`, `"report_back"`. Assign only the proposal's assumption reconciliation to QUALITY; no gateway/gate/network/companion changes are implied. [VERIFIED: docs/desk-operating-model.md:153-178; .planning/REQUIREMENTS.md:35-36]
2. QUALITY edits its own document slice, retains all unverified rows and produces its own genuine receipt/result. Use the existing cross-bot protocol, not ownership reassignment or a LEAD-authored foreign patch. A docs-only assumptions update does not require inventing a new API contract. [VERIFIED: docs/cross-bot-protocol.md:5,29-55; docs/desk-operating-model.md:138-151; ownership.yaml:239-240]
3. **Integration/CI constraint:** the root workflow derives one acting bot from the branch prefix and passes it to G-1. On `"bot-00-programming-lead/desk-swarm-subagents"`, a still-in-diff QUALITY-owned document is foreign to the acting LEAD. Separate owner receipts alone do not create a multi-owner G-1 exception. Keep the fixed LEAD branch unchanged; parent must route QUALITY's document through an owner-attributed PR/slice and an actual integration/base arrangement that does not leave a foreign document in a LEAD-only gate diff. An already reviewed/landed owning PR can supply that source result, subject to actual merge authority; this researcher creates or merges no branch/PR. If that route/authority is unavailable, retain a blocking integration checkpoint—not a green G-1 claim, a branch rename, a gate bypass or a destructive rebase of user work. [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:25; .github/workflows/gates.yml:70-99; ci/gates/check_ownership.py:143-163; docs/cross-bot-protocol.md:46-54]
4. QUALITY cannot approve a QUALITY-authored receipt; the document's independent review must come from LEAD or an actual human. The consolidated LEAD work still requires independent QUALITY review where requested. Keep evidence authorship and approval identity distinct. [VERIFIED: docs/quality-gates.md:278-285; docs/desk-operating-model.md:198-207]
5. Main consolidates after the owned slices and actual human observations land. A missing nested/healthy brief or revision marker requires a real scoped human loop acknowledgement during specialist execution; the parent-observed HTTP `503` does not establish a successful turn-start brief. No researcher fabricates a brief, acknowledgement, event/retain success or signed handoff. [VERIFIED: docs/desk-operating-model.md:140-146; .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.json:192-204; .planning/intel/constraints.md:65]

### §13 Reconciliation Checklist for QUALITY

The following are **required dispositions**, not edits performed here. Original assumption values/rows are opened at proposal lines 338–349. [VERIFIED: docs/upgrade-plan-desk-v2.md:338-349]

| Existing §13 subject | Required evidence-backed disposition |
|---|---|
| Railway service/default visibility | Replace the historical visibility/default-only account with the parent's actual scopes/service/listener results; retain authorization, private-DNS/traversal and unobserved-environment limits. |
| Bot UUID and prompt path | Add the actual selected Bot trace/path and write/readback result only when obtained. Until then retain documented-target-only status. |
| MCP list-change | Record actual client/protocol and delivered-notification result, or observed non-support plus exercised fallback. Distinguish source emission expectation from an actual trace. |
| Bot creating another Bot | Keep unverified and not relied upon. Do not turn this into a new n1 investigation or approval capability. |
| Cursor team tier/network policy | Record actual authenticated tier and effective mode/group policy; identify later allowlist need. Public docs are not the account result. |
| railway-app project/role | Correct unknown project with hostname evidence; retain bounded subnet-advertiser role and later suitability/disposition/retirement gates. |
| Root GitHub Actions | Correct root-absence history with opened root source; leave remote activation/runner/current run unverified unless genuine evidence exists. |
| Play/App Store credentials | Record ownership/availability metadata only; retain later n4.3 access/action requirements and no leaked values. |
| Hindsight version/model | Distinguish the template assumption from the configured image; add actual version/provider/model/dimension evidence before any first Desk write. No compatibility/upgrade inference from a health response or missing metadata. |
| Cursor intake triggers | Record actual account-integration availability; retain ten-minute polling floor and later n6.3 execution/acknowledgement. |
| Original-session and E2E statement | Preserve the fact that the original authoring session did not create trackers/deploy/merge. Add subsequent real evidence as subsequent history, without falsely making the full uplift-to-merge-to-sync E2E path verified. |

### Exact-SHA Approval Is a Real Prerequisite, Not a Stamp Workaround

The authoritative head rule says “An approval must be bound to a sha, and must not create one.” Its specified reference is `"approval_ref"` with `"kind"` (`"check_run"`, `"pr_review"` or `"gateway_store"`), `"name"` and `"reviewed_sha"`, resolved against the current head. These are **specified mechanisms**, not capabilities this phase has proved available. [VERIFIED: docs/desk-operating-model.md:209-240]

The opened implementation of `receipt_approve` now gates a stamped candidate and compares the read tip before `_commit_file`, but still calls that function to commit and push the approval. `_commit_file` explicitly invokes `"commit"` and `"push"`; compare-and-push race protection does not make that new tip reviewed. Do not use this operation for the locked no-new-tip approval. [VERIFIED: services/desk-gateway/src/desk_gateway/tools/quality.py:148-189,306-349]

Recommendation: Main obtains a genuine independent review/approval for the exact final candidate SHA through an actually available non-commit mechanism and confirms the existing gate/review route can consume the evidence. Commit candidate artifacts before review, never add an on-branch approval stamp afterward, and invalidate clearance if the tip moves. Do not assume a GitHub token can create check runs, a gateway-store approval endpoint exists, or the current checker resolves the specified reference. If that capability/gate path is unavailable, keep review/merge/phase progression blocked and route the prerequisite through its actual owner and authorized phase boundary. Implementing the approval resolver is not an n1 shortcut; its retained delivery is `"REQ-GATEWAY-036–038"` and `"REQ-ACCEPT-006"`. [VERIFIED: .planning/INGEST-CONFLICTS.md:30-32; docs/desk-operating-model.md:226-240; .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:29]

## Complete Source-Step Crosswalk — Kickoff Must Retain All 41

Source graph node/step identity is preserved: n1–n6 have six steps each; n7 has five. The tables below copy the roadmap's **Retained delivery** and **Requirement / consumer trace** cells; they are tracking and downstream-boundary references, not claims of execution. Store the full original step prose in actual child rows and carry the resolved weekly/XPS/human-activation/exact-SHA clarifications, rather than use this abbreviated matrix as a new brief. [VERIFIED: docs/upgrade-plan-desk-v2.md:314-330; .planning/ROADMAP.md:35-42,60-67,86-93,115-122,141-148,169-176,197-203]

### n1 — Current Phase 1 Delivery

| Source step | Retained delivery (verbatim) | Requirement / consumer trace (verbatim) |
|---|---|---|
| `n1.1` | List both Railway projects' actual service names, ports and environments in authorized account | REQ-INVENTORY-004 |
| `n1.2` | Identify railway-app node | REQ-INVENTORY-005, REQ-NETWORK-015 |
| `n1.3` | Prove Bot UUID read and own SYSTEM_PROMPT.xml write, exact path | REQ-INVENTORY-006, REQ-INVENTORY-007 |
| `n1.4` | Observe tools/list_changed support or use fallback | REQ-INVENTORY-008, REQ-GATEWAY-049, REQ-GATEWAY-050 |
| `n1.5` | Confirm Cursor network policy and plan tier | REQ-INVENTORY-009, REQ-INVENTORY-010 |
| `n1.6` | Record results in plan §13 through QUALITY docs ticket | REQ-INVENTORY-011 |

[VERIFIED: .planning/ROADMAP.md:37-42]

Kickoff requirements `"REQ-INVENTORY-001"`, `"REQ-INVENTORY-002"`, `"REQ-INVENTORY-003"` and path/prerequisite requirements `"REQ-INVENTORY-012"` through `"REQ-INVENTORY-016"` are **additional Phase 1 coverage**, not extra source steps or a reason to omit the six n1 steps. Their source boundaries are explicit in the requirements block. [VERIFIED: .planning/REQUIREMENTS.md:15-20,37-46]

### n2 — Network Plane, Inventory Now / Implementation Later

| Source step | Retained delivery (verbatim) | Requirement / consumer trace (verbatim) |
|---|---|---|
| `n2.1` | Deploy/adopt Ultrathink forwarder with five mappings, tag and disabled expiry | REQ-NETWORK-001, REQ-NETWORK-003, REQ-NETWORK-004 |
| `n2.2` | Deploy/adopt Agent Substrate forwarder for Hindsight/RAGFlow | REQ-NETWORK-002, REQ-NETWORK-003, REQ-NETWORK-004 |
| `n2.3` | Apply exact-port deny-default ACL for VPS, Mac mini and XPS; evidence each permitted device path | REQ-NETWORK-005, REQ-NETWORK-006, REQ-NETWORK-007, REQ-NETWORK-021, REQ-NETWORK-022 |
| `n2.4` | Cut substrate environment over, restart, verify brief/events | REQ-NETWORK-008, REQ-NETWORK-009, REQ-NETWORK-010, REQ-NETWORK-019 |
| `n2.5` | Approved G-6 public Timescale/Greptime retirement and rollback | REQ-NETWORK-011, REQ-NETWORK-012, REQ-NETWORK-013, REQ-NETWORK-014 |
| `n2.6` | Receipt with tailnet status, probes and unverified limits | REQ-NETWORK-020 |

[VERIFIED: .planning/ROADMAP.md:62-67]

Retain cross-cutting `"REQ-NETWORK-015"` (n1.2 suitability decision), `"REQ-NETWORK-016"` (Bots use HTTPS/no DB credentials), `"REQ-NETWORK-017"` (n4.5 allowlist) and `"REQ-NETWORK-018"` (INFRA-only emergency desktop-egress documentation); they are not lost because the primary six-step table does not list all four. n2 depends on verified n1. [VERIFIED: .planning/REQUIREMENTS.md:78-85; .planning/ROADMAP.md:46]

### n3 — Companion Data Planes, Prerequisites Only in Phase 1

| Source step | Retained delivery (verbatim) | Requirement / consumer trace (verbatim) |
|---|---|---|
| `n3.1` | Gated companion docs/env/GSD replan integration | REQ-DATA-001..006 |
| `n3.2` | Hindsight write/read/banks/redaction/version; back up and retire local memory paths | REQ-DATA-007..016, REQ-INVENTORY-013 |
| `n3.3` | Dragonfly brief/search/recall/rate caches with fail-through, cache only | REQ-DATA-017..022 |
| `n3.4` | Desk Timescale coordination migrations, hypertables and aggregates | REQ-DATA-023..029 |
| `n3.5` | RAGFlow dataset ingest and docs_search integration | REQ-DATA-033..037 |
| `n3.6` | Package receipts with actual bun test evidence | REQ-DATA-038 |

[VERIFIED: .planning/ROADMAP.md:88-93]

Retain additional `"REQ-DATA-030"`, `"REQ-DATA-031"`, `"REQ-DATA-032"`: redacted append-only event chain, hourly devnet ledger anchoring and export beyond 180 hot days. n3 depends on verified n2; n1 does not implement compatibility, banks, migrations, scheduling or companion changes. [VERIFIED: .planning/ROADMAP.md:71,95; .planning/REQUIREMENTS.md:155-160]

### n4 — Gateway and Contracts, No Implementation in This Slice

| Source step | Retained delivery (verbatim) | Requirement / consumer trace (verbatim) |
|---|---|---|
| `n4.1` | Seven roster and three initial pack contracts, consumers ack, contract first | REQ-GATEWAY-001..003, REQ-INVENTORY-016 |
| `n4.2` | Seat OAuth/routing, eight core tools and Greptime audit | REQ-GATEWAY-004..008, REQ-GATEWAY-012..020, REQ-GATEWAY-029, REQ-DATA-030 |
| `n4.3` | All seat tools, g5/g6, deadlines/failures, pack behavior and roster fixtures | REQ-GATEWAY-021..034, REQ-GATEWAY-036..039, REQ-GATEWAY-047..053, REQ-INVENTORY-012 |
| `n4.4` | Origin-token intake API and LEAD-only intake tools | REQ-GATEWAY-040..046 |
| `n4.5` | Public DNS/nginx/TLS/systemd/env and needed allowlist | REQ-GATEWAY-009..011, REQ-NETWORK-017 |
| `n4.6` | Scratch-Bot smoke: two distinct lists and wrong-seat 403 | REQ-GATEWAY-006, REQ-GATEWAY-007, REQ-GATEWAY-035 |

[VERIFIED: .planning/ROADMAP.md:117-122]

Final gateway verification depends on Phase 3. Only the skeleton overlap may start **after verified Phase 1**; that permission does not move gateway implementation into this researcher or certify final gateway work. `"REQ-GATEWAY-054"` is retained with the actual mobile action in n6.4. [VERIFIED: .planning/ROADMAP.md:99,111,174]

### n5 — Prompts, Skills, Templates, Plugin; Human Activation Later

| Source step | Retained delivery (verbatim) | Requirement / consumer trace (verbatim) |
|---|---|---|
| `n5.1` | Placeholders/roster assembly/core PD-8/G-7 and fixtures | REQ-SHARE-001..003, REQ-SHARE-007, REQ-SHARE-039, REQ-INVENTORY-014 |
| `n5.2` | Every seat prompt sections, assembly and parsing | REQ-SHARE-004..009 |
| `n5.3` | All seven §8.2 skills authored and reviewed with authorized lifecycle | REQ-SHARE-008, REQ-SHARE-010, REQ-SHARE-019, REQ-SHARE-040 |
| `n5.4` | swc-programming-desk plugin and companion grok-bot projector | REQ-SHARE-011, REQ-SHARE-012, REQ-SHARE-014, REQ-SHARE-040 |
| `n5.5` | Seven actual Team-only templates and Share-card screenshots | REQ-SHARE-015..022 |
| `n5.6` | Desk pack skills_propose PR into agent-skills | REQ-SHARE-013 |

[VERIFIED: .planning/ROADMAP.md:143-148]

Retain `"REQ-SHARE-023..038"` bootstrap/doctor invariant coverage and the actual human installation/publication gate. n5 depends on verified n4. Source/private-library presence, review PRs or generated template descriptions do not establish activated/published assets. [VERIFIED: .planning/ROADMAP.md:126,131-137,150]

### n6 — Real Fresh-desk Acceptance, Not a Phase 1 Smoke Substitute

| Source step | Retained delivery (verbatim) | Requirement / consumer trace (verbatim) |
|---|---|---|
| `n6.1` | Fresh recipient adds seven templates, bootstraps and seven doctors green | REQ-ACCEPT-001, REQ-ACCEPT-002, REQ-SHARE-023..038 |
| `n6.2` | Docs-only LEAD ask, double uplift/ticket/pending result, independent exact-SHA approval | REQ-ACCEPT-003..007, REQ-ACCEPT-020..034, REQ-GATEWAY-036..038 |
| `n6.3` | GitHub-label and curl-origin intake, LEAD acknowledgement to issue/origin | REQ-ACCEPT-008, REQ-ACCEPT-009, REQ-INVENTORY-015, REQ-GATEWAY-040..045 |
| `n6.4` | Actual iOS message and push-notification g5 approval | REQ-ACCEPT-010, REQ-ACCEPT-011, REQ-GATEWAY-054 |
| `n6.5` | Gateway/forwarder/cache/wrong-seat/pack-ceiling failure drills | REQ-ACCEPT-012..017 |
| `n6.6` | Open acceptance questions to Ove capped at four | REQ-ACCEPT-018 |

[VERIFIED: .planning/ROADMAP.md:171-176]

Retain mandatory closure `"REQ-ACCEPT-019"`; n6 depends on verified n5. Human fresh-recipient/iOS/loop-ack/reviewer actions are real prerequisites, not automatic answers. [VERIFIED: .planning/ROADMAP.md:154,165,178]

### n7 — Ordered Rollout and Rollback, Entirely Later

| Source step | Retained delivery (verbatim) | Requirement / consumer trace (verbatim) |
|---|---|---|
| `n7.1` | Source order with allowed gateway skeleton overlap | REQ-ROLLOUT-001, REQ-ROLLOUT-012 |
| `n7.2` | Network/env/gateway/prompt/template rollback evidence | REQ-ROLLOUT-002..006 |
| `n7.3` | Desk cutover windows and dispatch-note audit trail | REQ-ROLLOUT-007, REQ-ROLLOUT-008 |
| `n7.4` | PR-field sync and Ove report with all receipt paths/unverified | REQ-ROLLOUT-009, REQ-ROLLOUT-010 |
| `n7.5` | If superseded, retire railway-app after n6 with G-6 approval | REQ-ROLLOUT-011 |

[VERIFIED: .planning/ROADMAP.md:199-203]

Retain mandatory closure `"REQ-ROLLOUT-013"`. n7 depends on verified Phases 2–6; node identity never supplies retirement authority. No source step or requirement is discarded by Phase 1's narrower **execution** boundary. [VERIFIED: .planning/ROADMAP.md:182,193,205; .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:83]

## Don't Hand-Roll

| Problem | Do not build/use | Reuse instead | Grounding |
|---|---|---|---|
| Tracker materialization | A second tracker model, guessed IDs, partial graph or fake URL map | Existing kickoff hierarchy/idempotency and actual mounted tool schemas | `"Parent Item"` links Issue→Task and Sub-Issue→Issue; all source steps required. [VERIFIED: vendor/ultrathink-policy/kickoff-checklist.md:35-68; .planning/REQUIREMENTS.md:17-20] |
| Bot identity/file proof | Server-side prompt hints, static rosters or fixture UUIDs | Actual selected Bot/native computer trace and preserved-byte write/readback | Caller supplies `"agent_uuid"`; renderer returns `"install_path_hint"`. [VERIFIED: services/desk-gateway/src/desk_gateway/tools/core.py:203-225] |
| Tool-list fallback | New notification service/connector/server fixture | Existing same-seat `/mcp/<seat>/packs/<app>` route plus actual human client evidence | Source discovery and documented fallback are reusable but not exercised acceptance. [VERIFIED: services/desk-gateway/src/desk_gateway/server.py:46,81-105; skills/tool-packs/SKILL.md:83-90] |
| Account policy | Inferring plan/policy from tool absence, failed relay or local peer state | Actual authenticated tier/effective policy and product docs | Parent records timeout; actual account evidence remains missing. [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.md:37,39; CITED: https://docs.x.ai/grok-bot/security] |
| Credential inventory | Dumping tokens, minting keys, calling release/status adapters | Private owner/account availability metadata | Environment readers and Play edit side effect are opened source. [VERIFIED: services/desk-gateway/src/desk_gateway/config.py:169-172; services/desk-gateway/src/desk_gateway/tools/mobile.py:18-29] |
| Independent approval | Approval-as-commit, placeholder approver or invented approval endpoint | Actually available exact-SHA non-commit independent review; otherwise checkpoint | “An approval must be bound to a sha, and must not create one.” [VERIFIED: docs/desk-operating-model.md:209-240] |
| Ownership | First-match resolution, manifest changes to permit a foreign edit | Ordered resolver and separate owner-attributed delivery | “Last matching rule wins”; foreign paths fail. [VERIFIED: ci/gates/check_ownership.py:62-72,143-163] |

## Common Pitfalls

### 1. Treating Access Failure as Product Non-support

**Failure:** Declaring the SaaS client unsupported, the team non-Enterprise or credentials absent because an access mechanism fails. **Cause:** Confusing harness/local connectivity with the separate account/client. **Avoid:** Keep the parent facts “failed DNS ETIMEOUT,” “timed out after 12000ms,” and the offline peer/tool-registry observation as bounded failed access. Require actual authenticated evidence. **Warning:** A negative capability claim cites only one of those failures. [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.json:163-190,219-222; .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.md:39]

### 2. Testing the Wrong Subject

**Failure:** Renderer/hash/roster tests pass and are presented as UUID/file-write or client-notification acceptance. **Cause:** Fixtures and server metadata answer different questions. **Avoid:** Actual Bot identity/file trace and actual client discovery after delivered notification. **Warning:** The evidence contains only the literal path hint or caller-supplied identity/hash. [VERIFIED: services/desk-gateway/src/desk_gateway/tools/core.py:203-240; .planning/REQUIREMENTS.md:25-30]

### 3. Assuming the Server Emitted a Notification

**Failure:** Blaming the client when no valid notification/stream has been observed. **Cause:** The skill promises emission while the opened load method only updates state and returns a next-list note; negotiated transport is also unknown. **Avoid:** Capture emission/delivery before drawing client conclusions, and use the matching protocol's notification mechanism. **Warning:** No notification trace, transport or protocol version accompanies a non-support conclusion. [VERIFIED: services/desk-gateway/src/desk_gateway/tools/packs.py:17-39; skills/tool-packs/SKILL.md:80-81; CITED: https://modelcontextprotocol.io/specification/2025-11-25/server/tools; https://modelcontextprotocol.io/specification/2026-07-28/server/tools]

### 4. Promoting Configuration or Health to Compatibility/Cutover

**Failure:** Calling the Hindsight image the live version, dimensions a default, or HTTP transport success healthy substrate. **Cause:** Config, response fields, container listeners and authenticated behavior are different evidence classes. **Avoid:** Preserve actual subject/output and obtain running version/dimension evidence before first storage; Phase 3 proves actual adapter behavior. **Warning:** Curl exit `0` masks HTTP `503`, or the template `"v0.10.1-slim"` becomes a runtime version. [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.json:192-217; docs/upgrade-plan-desk-v2.md:346]

### 5. Silent Tracker Compaction or Duplicate Dispatch

**Failure:** Seven nodes become fewer issues/steps after quota/permission failure, or re-entry starts a second agent. **Cause:** Applying a generic fallback/default over the locked full graph and human gates. **Avoid:** Preserve real successes/failures, resume the same graph, stop on quota and separately check dispatch identity. **Warning:** Missing child URLs are normalized as a complete kickoff. [VERIFIED: skills/gotxcot-uplift/SKILL.md:152-159,187-194; skills/trackplan-dispatch/SKILL.md:195-204; .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:24,32]

### 6. Ownership or Review Laundering

**Failure:** LEAD edits §13, a bot-00 PR claims mixed owner paths pass ordinary G-1, QUALITY approves its own document, or a stamp commit is called exact-head approval. **Cause:** Assuming coordination, branch compare-and-push or a manifest comment grants authority. **Avoid:** Separate actual owning slice/PR, independent reviewer and no-new-tip approval. **Warning:** Foreign document remains in the LEAD diff, approval SHA differs from current tip, or `approved_by` is self-filled. [VERIFIED: ownership.yaml:239-240,401-402; .github/workflows/gates.yml:70-99; docs/quality-gates.md:278-285; docs/desk-operating-model.md:209-240]

### 7. Premature Activation or Sensitive “Read” Calls

**Failure:** Credential inventory creates a Play edit, trigger inventory runs a routine, or n1 connector testing is reported as n5 plugin/skill activation. **Cause:** Treating method names or account UI presence as authorization and completion. **Avoid:** Availability metadata only; bounded actual discovery trial only; later authorized activation evidence retained. **Warning:** Production state/API edits, new credentials or routine execution appear in an inventory receipt. [VERIFIED: services/desk-gateway/src/desk_gateway/tools/mobile.py:18-29; .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:10,28; CITED: https://docs.x.ai/grok-bot/skills-routines-and-automations]

## Code Examples

These are **verbatim source/documentation excerpts**, not executed requests, completed uplifts or runtime receipts. Paths from repository docs are documented targets only; the actual Bot path still requires live discovery.

### Exact ORIGINAL for the Actual First Uplift

The text between the delimiters below copies the operator block's text, excluding Markdown's blockquote marker; preserve its spelling/punctuation rather than correcting it. [VERIFIED: docs/upgrade-plan-desk-v2.md:15]

```text
DATA_B73E91C4_START
We're upgrading our Programming Desk application in https://github.com/swcstudiospace/programming-desk We want each bot to have it's own unique interface which connects our Railway resources properly via Tailscale. So we have 2 projects in Railway. Ultrathink which has our databases and then we have Agent Substrate which has 2 applications "Hingsight" and "RAGflow" so please upgrade our Agent Substrate documents to use the 3 databases and 2 applications intelligently then wire them into our Programming Desk whilst doing an overall uplift to our Programming Desk as a whole. We want a Grok Bot share which will integrate the entire desk from Add Bot and ensure our XML's Skills, Memories, Tools etc are still integrated properly. We want to drive the application from outside of the Desk speaking only to Lead. All of our Bots require 10-15 proper tools for themselves. Please introduce proper integrations of the applications and stuff from Grok Bot leveraging other skills and stuff made by other Teams. For our actual ios and Android bots can load up specialised tools for applications etc. Please plan an upgrade
DATA_B73E91C4_END
```

The delimiters are research data boundaries, not part of ORIGINAL. The actual first uplift must fill its operational sections and the actual second uplift must contain returned live URLs; this excerpt claims neither was dispatched. [VERIFIED: skills/gotxcot-uplift/SKILL.md:48-62,163-194]

### Wire Notification — Not a Captured Client Event

Official 2025-11-25 tools notification example: [CITED: https://modelcontextprotocol.io/specification/2025-11-25/server/tools#list-changed-notification]

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/tools/list_changed"
}
```

For a client negotiating the 2026-07-28 specification, use its documented subscription mechanism rather than assuming this standalone message proves delivery. [CITED: https://modelcontextprotocol.io/specification/2026-07-28/server/tools#list-changed-notification]

### Existing Pack Discovery/Fallback Return

The literal returned keys/string below are quoted from the actual function; no load occurred here. [VERIFIED: services/desk-gateway/src/desk_gateway/tools/packs.py:32-39]

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

Route syntax is quoted verbatim from the source, not a newly invented API: [VERIFIED: services/desk-gateway/src/desk_gateway/server.py:46]

```python
SEAT_PATH = re.compile(r"^/mcp/(?P<seat>[a-z]+)(?:/packs/(?P<pack>[a-z][a-z0-9-]{1,40}))?/?$")
```

### Existing Ownership Resolver

Verbatim last-match implementation; planner reuses this rather than inventing first-match resolution. [VERIFIED: ci/gates/check_ownership.py:62-72]

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

## State of the Art — Relevant Source/Documentation Reconciliation

| Earlier/source assumption | Current documented/source observation | Planning impact |
|---|---|---|
| §13: root `.github/` absent | Opened root `name: Quality Gates`, PR/push `[main]` declarations | Correct history; require actual remote/run/runner evidence before calling CI active. [VERIFIED: docs/upgrade-plan-desk-v2.md:344; .github/workflows/gates.yml:23-40] |
| Template `v0.10.1-slim` is the Hindsight assumption | Parent configured `ghcr.io/vectorize-io/hindsight-api:0.9.1`; real version/model/dimensions unknown | Inventory the real deployment; no automatic upgrade or compatibility claim. [VERIFIED: docs/upgrade-plan-desk-v2.md:346; .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.md:20,36] |
| Source n6.2 uses an on-branch approval stamp | Current rule requires exact SHA and no new tip; current approval function still commits | Preserve the independent-review intent, reject the stamp workaround and checkpoint actual capability. [VERIFIED: .planning/INGEST-CONFLICTS.md:30-32; services/desk-gateway/src/desk_gateway/tools/quality.py:174-189,338-349] |
| Notification message alone described by 2025-11-25 tools docs | 2026-07-28 tools docs specify notification delivery on a subscription stream | Capture negotiated protocol; do not conflate protocols or silently upgrade. [CITED: https://modelcontextprotocol.io/specification/2025-11-25/server/tools; https://modelcontextprotocol.io/specification/2026-07-28/server/tools] |
| Generic “private computer per Bot” intuition | Official docs state account-wide shared files/browser credentials/connectors | Verify self-namespace and human account scope; do not put private platform secrets there. [CITED: https://docs.x.ai/grok-bot/computer-and-apps] |

## Assumptions Log

No training-only technical claim is used as a locked decision or tagged `[ASSUMED]`. Unknown runtime/account facts remain **missing evidence**, not guessed defaults: actual Bot UUID/path, client notification delivery/result, Cursor tier/effective policy, credential availability/ownership, Hindsight version/dimensions, tracker permissions/current graph state and active GitHub/runner/review capabilities. These are explicitly routed below. A missing field, failed access or source-only fixture is not evidence of incompatibility or absence. [VERIFIED: .planning/REQUIREMENTS.md:15-46; .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:18-29]

| # | Claim tagged ASSUMED | Section | Risk if wrong |
|---|---|---|---|
| — | None; no unverified default has been promoted to a decision | — | Human/runtime evidence is still mandatory; an empty assumptions table is not a passed phase. |

## Open Questions and Concrete Human-action Boundaries

These are evidence-acquisition checkpoints for the downstream planner, **not unanswered design preferences** or requests to narrow scope. Research can be planned now; actual execution must stop at the missing prerequisite. The context explicitly requires a “blocking human-action checkpoint” and says a deferral “is a resumable stop, not dependency clearance.” [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:21,29]

| Checkpoint | Actual missing prerequisite / what is already known | Actor and concrete action | Resume condition and boundary |
|---|---|---|---|
| Authorized accounts and complete tracker kickoff | Parent Railway identity is not established as Ove's. Notion/Linear schemas are mounted/read, but actual writable collection/schema/team/quota and existing graph/dispatch identity were not queried in this research. | Authorized project/account owner confirms target scope; LEAD uses real tracker tools to fetch/query/discover/update all rows. If auth/quota/schema fails, owner supplies access/correct destination without a private-draft substitute. | Actual scoped identity and complete returned graph URL map; no fake IDs, tracker-less waiver, compact mode or duplicate dispatch. |
| Actual Bot filesystem and client trial | Parent has no successful self-UUID/prompt trace. Browser relay timed out; mounted UUID/prompt tools absent; public gateway DNS failed. None proves SaaS non-support. | Human opens the actual authenticated desktop Bot/Agent Computer, completes sensitive login steps, supplies own-identity/write/readback evidence. For discovery, human/SYSTEMS supplies an available authorized real connector and delivered-notification/client trace or actual exercised fallback. | Required subject-specific evidence exists, including actual path/UUID and client result. If public/auth/notification preconditions are unavailable, stop rather than fix gateway/network in n1 or substitute fixtures. |
| Cursor team policy/tier and trigger controls | Actual tier/policy/event availability missing; only a relay timeout and official product constraints exist. | Actual team/admin owner captures billing/plan identity, effective team/group Bot network mode and account-integration controls. Never paste session cookies/passwords or enable routines for inventory. | Actual policy/tier and trigger-availability record. Later allowlist/trigger activation stays n4.5/n6.3; retain polling floor. |
| Private credential and Hindsight prerequisites | No actual mobile credential availability/ownership or running Hindsight version/dimensions was supplied. Configured image/public health are bounded evidence only. | INFRA plus Play/Apple account owners provide non-secret availability/custody/scope metadata; SYSTEMS/runtime owner provides the API's actual version and effective embedding-space evidence, preserving existing data. | Availability is truthfully classified; required Hindsight prerequisites established before first Desk storage. No new credential, API, upgrade, retain, migration or companion edit in this slice. |
| Owned §13 integration, current CI and exact-SHA review | Root workflow source exists; remote registration/current run/runner evidence and usable no-new-tip gate/review capability are not established. Mixed owner changes on the fixed LEAD branch conflict with single-bot G-1. | LEAD routes real n1.6 ticket; QUALITY owns document slice; parent arranges owner-attributed delivery/base and independent review. INFRA/account owner supplies actual GitHub workflow/runner facts. Main confirms actual final-SHA gate/review evidence. | Real owned §13 result, independent non-self/non-commit review and actual consolidated verification. If required capability or integration authority is unavailable, keep the phase/gate pending; do not invent approval or change ownership. |

Missing prerequisite facts above are supported by the bounded inventory and source/schema reads, **not a new claim that every service/account is inaccessible**. The authenticated Bot/Cursor relay/public-gateway attempts are known failed access; tracker/mobile/Hindsight metadata and remote CI permissions are simply not established in this research. [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.md:7,33-41,47-56; CITED: xd://mcp__notion_create_pages; xd://mcp__linear_save_issue; xd://mcp__railway_describe_environment]

## Environment Availability

No runtime probes or installation/version checks were performed by this worker. The audit below distinguishes parent observations, declared versions, mounted schemas and missing runtime evidence; it does not turn a declared dependency into an installed one.

| Dependency | Required by | Available evidence | Version / scope | Fallback or action |
|---|---|---|---|---|
| Railway account/service read access | n1.1/n1.2 | Parent actual reads and six SSH command/result records | The quoted production project/environment/service IDs above; account authorization unresolved | Reuse record, confirm owner scope. Do not replay failed logs/ss checks. [VERIFIED: 01-INVENTORY.md:7-28,41; 01-INVENTORY.json:32-39] |
| Actual Bot native computer/client | n1.3/n1.4 | No successful actual Bot trace; offline peer/tool absence is only bounded access evidence | Actual UUID/path/client version unknown | Human actual-client action; no server/fixture substitute. [VERIFIED: 01-INVENTORY.md:39,49-50] |
| Public gateway/OAuth/notification delivery | n1.4 | Loopback health only; public DNS access failed | Parent loopback reports `"0.1.0"`, `"registered_seats": []`, `"channel_registered": false` | Actual owner supplies working authorized evidence path; otherwise checkpoint, not n1 networking implementation. [VERIFIED: 01-INVENTORY.json:171-190] |
| Authenticated Cursor admin/billing/integration UI | n1.5 and prerequisites | Parent relay timed out; no actual team result | Tier/effective policy/triggers unknown | Human admin capture, no tier inference. [VERIFIED: 01-INVENTORY.json:219-222] |
| Notion/Linear connections | Kickoff | Tool schemas available; real resource access/quota not exercised here | Source-configured destination/team, actual schema/IDs to discover | Use mounted tools during execution; checkpoint actual failure. [CITED: xd://mcp__notion_fetch; xd://mcp__linear_list_teams; xd://mcp__linear_save_issue] |
| Mobile credentials | n4.3 prerequisite | Reader names only; no values/presence inspected | `PLAY_ACCESS_TOKEN`, `ASC_KEY_ID`, `ASC_ISSUER_ID`, `ASC_PRIVATE_KEY_PATH` | INFRA/account-owner metadata, no secret listing or release probe. [VERIFIED: services/desk-gateway/src/desk_gateway/config.py:169-172] |
| Running Hindsight API and embedding space | n3.2 prerequisite | Parent public health and configured image | `"ghcr.io/vectorize-io/hindsight-api:0.9.1"` configuration, not live version; dimensions unknown | Owner-provided actual version/model/dimension record before data. [VERIFIED: 01-INVENTORY.md:20,36] |
| Substrate production-loop brief | Specialist execution context | Parent HTTP `503`, despite command exit `0` | `"index": false`, `"greptime": false`, `"eventsWritable": false` | No success inference. Actual healthy brief or genuine scoped human loop acknowledgement per governance; no fabricated acknowledgement. [VERIFIED: 01-INVENTORY.json:192-204; docs/desk-operating-model.md:140-146] |
| Root GitHub Actions and runner | CI prerequisite | Root source present; remote activation/current run/runner status unknown | `runs-on: [self-hosted, Linux, X64]`; declared Python `"3.12"` | Existing account/runner evidence; later activation work, no worker installation/rerun. [VERIFIED: .github/workflows/gates.yml:25-40,63-68,203-228] |
| Local test tooling | Main's future validation | Source commands/declarations only; installed versions unprobed | `"pytest>=8.0"` declared in gateway dev group | Main resolves availability before its authorized run; no new framework/install here. [VERIFIED: services/desk-gateway/pyproject.toml:32-41] |
| Companion current source | Future n3 | Later dirty checkout observation, not exact earlier map snapshot | Parent-observed HEAD `"21652a20a1b3ca98132e80ca76aadedc95c3369d"`, branch `"claude/greptime-events-ledger-7j1so8"` | Owner re-establishes applicability later; preserve user modifications/deletions/untracked work. [VERIFIED: .planning/intel/implementation-map.md:29-31] |

The short `01-INVENTORY.*` citations in this table resolve to this phase directory. Missing actual Bot/client/team and required approval/integration evidence have **no admissible source-only fallback**. Tracker access may be available but has not been tested; do not call it unavailable until an actual scoped call fails. Verified absent mobile credentials can be recorded as absent, but cannot satisfy later authenticated mobile integration. [VERIFIED: .planning/REQUIREMENTS.md:15-46; .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:18-29]

## Validation Architecture

Included because config explicitly says `"nyquist_validation": true`. This is a **future Main-owned validation plan**, not test/gate execution or a claim of coverage passing. [VERIFIED: .planning/config.json:9; .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:66]

### Test Framework

| Property | Value / provenance |
|---|---|
| Framework | Existing pytest infrastructure. Source `import pytest`; gateway dev declaration `"pytest>=8.0"`; actual installed version unknown. [VERIFIED: ci/tests/test_gates.py:26; services/desk-gateway/pyproject.toml:32-36] |
| Config | Gateway has `[tool.pytest.ini_options]`, `asyncio_mode = "auto"`, `testpaths = ["tests"]`; root CI explicitly selects `ci/tests/`. Do not treat the gateway's test-path setting as live-client acceptance. [VERIFIED: services/desk-gateway/pyproject.toml:39-41; .github/workflows/gates.yml:228] |
| Candidate quick run | `python3 -m pytest ci/tests/test_gates.py::TestG1Ownership ci/tests/test_gates.py::TestG2Receipts -q` — selects opened classes `"TestG1Ownership"` and `"TestG2Receipts"`; this is a proposed invocation, not exercised output. Runtime under 30 seconds is unmeasured; Main should measure/adjust sampling without reducing acceptance scope. [VERIFIED: ci/tests/test_gates.py:244-298,305-333] |
| Full existing gate suite | `python3 -m pytest ci/tests/ -v` — literal documented/root-CI command, not run here. [VERIFIED: ci/tests/test_gates.py:10; .github/workflows/gates.yml:228] |
| Consolidated gate entry point | Opened flags `"--bot"`, `"--base"`, `"--receipt"`, `"--change"`, `"--strict"` on `ci/gates/run_all.py`; supply actual actor/base/task receipt and change document only if applicable. Manifest self-check is separately `python3 ci/gates/check_ownership.py --validate-manifest`; do not invent a run_all `--validate-manifest` flag. [VERIFIED: ci/gates/run_all.py:25-31,36-66; .github/workflows/gates.yml:89-99] |

### Phase Requirements → Test/Evidence Map

The requirement IDs/descriptions are defined in the Phase Requirements table above. Existing gate tests validate gate behavior, **not** Bot/account/service acceptance; source/client fixtures never close the manual evidence rows. [VERIFIED: .planning/REQUIREMENTS.md:15-46; ci/tests/test_gates.py:3-10,264-269,307-333]

| Req ID | Behavior to validate | Type | Main's actual evidence/command | Existing coverage / gap |
|---|---|---|---|---|
| REQ-INVENTORY-001 | Exact original in actual first uplift | Artifact/manual review | Compare actual packet ORIGINAL to the opened §1 text; no invented XML validator CLI | Source protocol exists; actual packet/equality evidence needed |
| REQ-INVENTORY-002 | Complete real graph hierarchy and links | Live integration/manual | Actual Notion fetched rows and paginated Linear node/child results; reconcile 7/41 identities | Mounted schemas exist; materialization/readback missing |
| REQ-INVENTORY-003 | Full second XML and real dispatch | Live integration/manual | Actual packet/link map and actual dispatch result, not a Markdown URL table | Source protocol exists; real packet/dispatch missing |
| REQ-INVENTORY-004 | Actual scopes/service names/listeners | Evidence reuse + owner review | Original parent command supplement/results; scoped account confirmation | Parent observations reusable; authorization/DNS boundaries remain |
| REQ-INVENTORY-005 | Node project, bounded role/routes | Evidence reuse + owner review | Parent actual hostname and tailnet output; any further owner/config role evidence | Identity/routes reusable, forwarder suitability not accepted |
| REQ-INVENTORY-006 | Actual own UUID/path read | Manual actual Bot | Native self-identity/computer transcript with actual output | Missing; no mounted/server fixture substitute |
| REQ-INVENTORY-007 | Actual same-file preserved-byte write/readback | Manual actual Bot | Actual write/readback/equality result and bounded hashes/path | Missing; source path hint/doctor hash insufficient |
| REQ-INVENTORY-008 | Actual client notification or exercised fallback | Manual/live MCP integration | Delivered notification + actual client discovery; or demonstrated non-support and actual fallback discovery/disable | Missing; existing route/load source is not client proof |
| REQ-INVENTORY-009 | Actual effective network mode/gateway need | Manual authenticated admin | Team/group policy screenshot or real account control-plane result | Missing; public product policy insufficient |
| REQ-INVENTORY-010 | Actual team tier | Manual authenticated account | Actual team billing/plan evidence | Missing; access failure cannot classify tier |
| REQ-INVENTORY-011 | QUALITY-owned §13 result | Owned artifact + independent review | Actual specialist slice/receipt, source diff, independent exact-SHA review; parent gates after proper integration | Source checklist exists; owned result/routing/review still required |
| REQ-INVENTORY-012 | Non-secret credential availability/ownership | Manual private-owner review | Presence/custody/account-scope metadata, no secret values/API edit | Missing; config reader is not availability evidence |
| REQ-INVENTORY-013 | Running version/embedding dimensions before storage | Read-only runtime-owner evidence | Actual service/deployment-correlated version/model/dimension evidence | Missing; health/image not sufficient; compatibility remains n3 |
| REQ-INVENTORY-014 | Root and actually active CI when claimed | Source + GitHub/platform evidence | Opened root declaration plus actual applicable run/workflow/runner status; no worker rerun | Root present; activation/current success unverified |
| REQ-INVENTORY-015 | Actual trigger availability/poll floor | Manual account inspection | Actual account-integration controls, retained ten-minute fallback record | Missing account evidence; YAML/plugin presence insufficient |
| REQ-INVENTORY-016 | Last-match ownership and consumers | Gate unit tests + manifest/path review | Candidate quick command above; Main's actual G-1 manifest/path checks for each owning slice | Existing G-1 tests/source; actual planned-path/actor/consumer review still needed |

### Sampling Rate and Phase Gate

- **Per task commit:** Main selects the relevant existing quick gate subset and actual artifact/evidence review after its authorized task changes. Workers in this assignment do not run it.
- **Per wave integration:** Main verifies once after all disjoint owned slices land, using the full existing suite and applicable consolidated gates; do not storm tests against half-written sibling work.
- **Phase gate:** Full relevant gate/evidence review and genuine current-SHA independent approval, with every Phase 1 requirement actually supported. A healthy loopback endpoint or successful fixture suite does not replace the manual rows. No Phase 2 or skeleton dependency clearance from pending human evidence.

These recommendations retain the context's “checks and commits are parent-owned,” “only after actual plan completion” and “live human actions remain blocking checkpoints.” [VERIFIED: .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:29,66]

### Wave 0 Gaps — Evidence, Not a New Product Test Framework

Before execution, establish:

- Actual first/second uplift packets, real graph identity/complete returned URL map and dispatch provenance.
- An authorized participating Bot's self-identity, prompt-byte preservation and write/readback channel.
- Actual client/protocol/notification-delivery or fallback evidence path, including real public/authenticated connector access.
- Authenticated team tier/effective policy/trigger controls and private owner metadata for credentials/version/dimensions.
- An owner-attributed §13 delivery/integration route and an actually usable exact-SHA non-commit review/gate mechanism.
- Main's real local/remote test/runner availability and actual command outputs when it performs consolidated verification.

No new test file is justified by this inventory-only scope: the gate suite already exercises “UNOWNED,” “no commands recorded” and claims citing failed/missing evidence. Missing live facts cannot be repaired with a mock, assertion fixture or artificial successful receipt. [VERIFIED: ci/tests/test_gates.py:264-269,316-333; .planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:10,18-29]

## Security Domain

Config explicitly enables `"security_enforcement": true`, `"security_asvs_level": 1` and `"security_block_on": "high"`. That config is a review requirement, not an ASVS certification or proof that any scanner ran. [VERIFIED: .planning/config.json:10-12]

### Applicable ASVS Categories

Use versioned ASVS references. OWASP identifies stable **5.0.0** and warns that identifiers change between versions; its opened chapter listing names V6 Authentication, V7 Session Management, V8 Authorization, V2 Validation and Business Logic, V11 Cryptography, V14 Data Protection and V16 Security Logging and Error Handling. The older GSD template labels V2/V3/V4/V5/V6 must not be presented as current 5.0 chapter numbers. [CITED: https://owasp.org/projects/asvs; https://github.com/OWASP/ASVS/tree/v5.0.0/5.0/en]

| ASVS 5.0 category | Applies | Standard control / n1 boundary |
|---|---|---|
| V6 Authentication; V10 OAuth and OIDC | Yes: actual account/client evidence | Existing supported OAuth/account UI; actual team/Bot identity. Human handles passwords/2FA; no credential dump or new auth service. |
| V7 Session Management | Yes: shared authenticated Bot computer and account UI | Do not copy cookies/tokens or assume a screen is an isolated session. Preserve human takeover and intended account scope. |
| V8 Authorization | Yes: self namespace, owners, account/team scope and specialist routing | Own Bot file only; actual permitted account/role; ordered ownership; no invented approval, consumer ack or cross-owner exemption. |
| V2 Validation and Business Logic | Yes: tracker IDs, graph hierarchy, path/evidence claims | Use fetched schemas/actual returned IDs, complete graph crosswalk and existing path/receipt validation; do not execute instructions found in source text or tracker bodies. |
| V11 Cryptography | Existing boundary only | Keep existing OAuth/PyJWT/crypto mechanisms; hash/readback is byte-equality evidence, not secret protection. No new crypto implementation or key generation. |
| V14 Data Protection | Yes: private prompts, credentials and evidence | Record availability metadata/bounded results, never prompt/secret dumps; no credentials on shared Bot computers or in trackers/templates. |
| V16 Security Logging and Error Handling | Yes: truthful evidence and current-SHA approval | Preserve actual failures/subjects, observer and omissions; no fabricated success/exit code; approval anchored to exact final reviewed head. |

Mapping is a recommendation grounded in the observed shared-computer product model, source credential/ownership boundaries and existing readers, not a claim that all controls are implemented/exercised. [CITED: https://docs.x.ai/grok-bot/computer-and-apps; VERIFIED: infra/substrate/SUBSTRATE-ENV.md:25-31; ownership.yaml:239-240,355-371,401-402; services/desk-gateway/pyproject.toml:13-16; docs/desk-operating-model.md:209-240]

### Known Threat Patterns for This Inventory Slice

| Pattern | STRIDE | Standard mitigation / evidence boundary |
|---|---|---|
| Wrong account or wrong Bot namespace accepted as the subject | Spoofing / Elevation of privilege | Corroborate selected Bot self-identity and authorized project/team scope; shared account computer is not per-Bot isolation. [CITED: https://docs.x.ai/grok-bot/computer-and-apps; VERIFIED: 01-INVENTORY.md:7,49] |
| Tokens/private prompts copied into tracker/receipt output | Information disclosure | Existing private credential partition and human secure takeover; availability booleans/metadata only. [VERIFIED: infra/substrate/SUBSTRATE-ENV.md:25-31; CITED: https://docs.x.ai/grok-bot/computer-and-apps] |
| Fictional tracker IDs, approvals, runtime successes or command exits | Tampering / Repudiation | Actual returned IDs/URLs, genuine observations, source-specific evidence, independent exact-SHA review. [VERIFIED: skills/gotxcot-uplift/SKILL.md:152-159,187-194; docs/desk-operating-model.md:209-240] |
| Foreign-path edits or unowned new files | Elevation of privilege | Ordered resolver, owner-attributed slice/PR, real contract consumers; do not rewrite manifest for convenience. [VERIFIED: ci/gates/check_ownership.py:62-72,143-163] |
| Attacker-controlled PR gate scripts or titles/bodies become commands | Tampering / Elevation of privilege | Preserve trusted-base CI overlay and source/intake data boundaries; inventory does not execute tracker content. [VERIFIED: .github/workflows/gates.yml:46-60; .github/workflows/desk-intake.yml:21-25] |
| Discovery “probe” triggers a release/API edit or affects other Bots | Tampering | Read private availability metadata, avoid Play edit side effect, human scopes account-wide connector toggles and captures actual unload/disable. [VERIFIED: services/desk-gateway/src/desk_gateway/tools/mobile.py:18-29; CITED: https://docs.x.ai/grok-bot/computer-and-apps] |

## Sources and Research Method

### Primary — Opened Repository Definitions and Durable Evidence

- `.planning/phases/01-inventory-and-prove-assumptions/01-CONTEXT.md:8-32,39-69,81-83` — all D-01..D-08 locks, exact scope, routing and human stops.
- `.planning/REQUIREMENTS.md:9,15-46,78-93,155-170` — every Phase 1 requirement and retained cross-cutting network/data boundaries.
- `.planning/ROADMAP.md:5,19-42,44-95,97-205` — fixed seven-phase/41-step identities, every retained source-step crosswalk, dependency/overlap/human gates.
- `.planning/INGEST-CONFLICTS.md:18-36,42-60` — actual weekly/XPS/human-activation choices and exact-SHA/no-new-tip discrepancy resolution.
- `.planning/phases/01-inventory-and-prove-assumptions/01-INVENTORY.md:3-56` and `01-INVENTORY.json:5-39,45-71,145-222` — parent observations, actual command supplement, scopes/listeners/routes and bounded failed/missing evidence. These are reused records, not this researcher's commands.
- `.planning/intel/implementation-map.md:3-7,13-27,29-31` and `.planning/intel/constraints.md:10-55,65` — authored versus deployed evidence and companion applicability limits.
- `docs/upgrade-plan-desk-v2.md:15,47-50,180-190,294-349` — exact ORIGINAL, locked topology, fallback, all original node steps and §13 checklist.
- `skills/gotxcot-uplift/SKILL.md:46-62,148-194`, `vendor/ultrathink-policy/kickoff-checklist.md:20-90`, `skills/trackplan-dispatch/SKILL.md:195-204` — existing full XML, tracker hierarchy, idempotency and dispatch protocol.
- `ARCHITECTURE.md:198-201`; `services/desk-gateway/src/desk_gateway/tools/core.py:203-249` — documented prompt target versus caller-supplied doctor/registration evidence.
- `services/desk-gateway/src/desk_gateway/server.py:46,81-105,367-370`; `tools/packs.py:17-39`; `skills/tool-packs/SKILL.md:12-22,65-90` — actual source discovery/fallback/load behavior versus notification expectation.
- `services/desk-gateway/src/desk_gateway/config.py:169-172`; `tools/mobile.py:18-29`; `upstreams.py:336-356,538-614`; `infra/substrate/SUBSTRATE-ENV.md:25-31` — credential readers/custody, Play edit side effect and current Hindsight adapter boundary.
- `ownership.yaml:164-183,239-240,347-371,401-402,436-447`; `ci/gates/check_ownership.py:62-72,143-163` — executable last-match routing and consumers.
- `docs/desk-operating-model.md:138-178,198-240`; `docs/cross-bot-protocol.md:5,29-55`; `docs/quality-gates.md:278-295`; `skills/verification-receipts/SKILL.md:60-88,207-216`; `tools/quality.py:148-189,306-349` — owned tickets/receipts, independent review and current stamp/new-tip gap.
- `.github/workflows/gates.yml:23-99,108-153,203-228`; `.github/workflows/desk-intake.yml:1-25`; `ci/gates/run_all.py:25-66`; `ci/tests/test_gates.py:3-10,244-333`; `services/desk-gateway/pyproject.toml:1-41`; `.planning/config.json:4-12,29-43` — actual declarations, existing validation architecture and no claims of executed checks.

`tools/*` and `upstreams.py` shorthand in this list resolve under `services/desk-gateway/src/desk_gateway/`; `01-INVENTORY.*` resolves in this phase directory. Citations attest to opened source text, not runtime path creation or deployed acceptance.

### Official Documentation / Mounted Tool Schemas

- [Grok Bot computer/apps](https://docs.x.ai/grok-bot/computer-and-apps) — shared account computer, native file/command access, human sensitive-step takeover and account-wide connectors.
- [Grok Bot private networks](https://docs.x.ai/grok-bot/private-networks) and [security/network policy](https://docs.x.ai/grok-bot/security) — explicit Enterprise constraints, effective modes/groups and distinction from Cloud Agent policy.
- [Skills, routines and automations](https://docs.x.ai/grok-bot/skills-routines-and-automations) — actual documented UI and account-integration/plugin distinction, not the team's observed availability.
- [MCP tools 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) and [2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) — versioned tool-list notification and subscription contracts.
- [Hindsight versioned 0.9 docs](https://hindsight.vectorize.io/0.9) and [configuration](https://hindsight.vectorize.io/developer/configuration) — actual-version documentation selection and embedding-space/dimension caveats, not live-instance metadata.
- [Google Play API getting started](https://developers.google.com/android-publisher/getting_started) and [App Store Connect API](https://developer.apple.com/help/app-store-connect/get-started/app-store-connect-api/) — account access, permissions and private key-custody boundaries.
- [GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax) — root workflow-directory requirement.
- [OWASP ASVS](https://owasp.org/projects/asvs) and [stable 5.0 English chapters](https://github.com/OWASP/ASVS/tree/v5.0.0/5.0/en) — versioned category mapping, not exercised security certification.
- `xd://mcp__notion_fetch`, `xd://mcp__notion_search`, `xd://mcp__notion_query_data_sources`, `xd://mcp__notion_create_pages`, `xd://mcp__notion_get_async_task`, `xd://mcp__linear_list_teams`, `xd://mcp__linear_list_issues`, `xd://mcp__linear_save_issue`, `xd://mcp__railway_describe_environment` — read tool schemas only; no live account calls or tracker mutations. Railway description applies staged changes, so its future reads must distinguish `"live"`, `"staged-create"`, `"staged-delete"`, `"live-with-staged-changes"` from settled runtime evidence. [CITED: xd://mcp__railway_describe_environment]

### Provider/Confidence Method and Limitations

The read-only research-plan seam was used for the five external domains (MCP discovery, actual Bot/account prerequisites, Hindsight, CI/review, mobile authentication). It selected Context7, but no mounted Context7 fetch device was available; research therefore fetched the official sources above using the read tool rather than claiming a Context7 result. The actual classifier invocation `query classify-confidence --provider webfetch --verified` returned `"confidence":"LOW"`. The opened provider implementation only awards higher tiers for recognized authority/legitimacy inputs; unknown providers return `"LOW"`. This artifact keeps that conservative provider tier instead of fabricating a higher result. [VERIFIED: session read-only research-plan/classify-confidence results; /root/.claude/gsd-core/bin/lib/research-provider.cjs:46-67,76-87]

Repository discrete values are quoted from source-of-truth files opened in this session. Official pages are tagged CITED; they do not become live-client/account claims. No registry legitimacy verdict, installed-version check, compatibility falsification, runtime probe, test, gate, smoke, formatter, install, deploy, commit or push was performed by this researcher. Research cache writes and a git commit were skipped because this assignment permits only the canonical research artifact as a repository file write; parent owns verification/commits.

## Metadata

| Area | Confidence | Reason |
|---|---|---|
| Standard stack | LOW provider tier | Existing declarations and actual tool schemas are opened/quoted; no new package proposed, installed/current versions and actual account permissions not probed. |
| Architecture/execution path | LOW provider tier; source-grounded recommendations | Locked source responsibilities, all 16 requirements and all 41 steps retained. Runtime access, owning PR integration and no-new-tip gate capability remain explicit prerequisites. |
| Pitfalls | LOW provider tier; direct source/documentation evidence | Source/fixture/live distinctions, actual side-effecting Play edit, notification emission precondition, branch G-1 constraint and approval-as-commit are explicitly grounded rather than inferred as live failures. |

**Research date:** 2026-10-08.  
**Refresh recommendation:** Re-read account/client/provider schemas and runtime evidence before execution or after any relevant change; public protocol/account controls should be refreshed within seven days. This is a planning recommendation, not a promised support interval.  
**Ready for planning:** Yes — full-scope Phase 1 plans can now be written with explicit human-action/checkpoint and owned-slice dependencies.  
**Phase verified / downstream cleared:** No. Missing actual evidence and independent exact-current-SHA clearance remain blocking; research completion never normalizes them to passed.
