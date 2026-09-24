# GitHub SoT Orchestration — Cloud Agents, Hermes VPS, Greptile

**Locked:** 2026-09-24 (Sydney)  
**Audience:** Programming Lead wiring intake → trackers → runtime lanes → PR gates.  
**Status:** Design recorded. End-to-end not verified. Linear MCP connected (dense smoke passed). **TrackPlan dispatcher skill written** (`skills/trackplan-dispatch/`). **GoTxCoT double-uplift skill written** (`skills/gotxcot-uplift/`). **Greptile↔QUALITY merge-gate skill written** (`skills/greptile-merge-gate/`). Lane B control is `user-hermes-agent` (HTTP, connected) via `agent_bus_*`. Local stdio `user-hermes` was intentionally uninstalled on the desk host on 2026-09-24; do not rebuild `hermes-mcp-bridge.mjs`. A Lane B job that lands a draft PR is still not verified (see §Gaps).

**Density (locked):** GoT **5–8 nodes**, CoT **4–8 steps per node** (each step a Linear sub-issue), CoT fill **sequential by default**, **two uplift passes**. The dispatcher consumes the **second** uplift (live Notion and Linear URLs inside the XML). Compact Linear remains quota-fallback only.

Companion to dense Linear + Notion kickoff: [`gotxcot-cloud-pipeline.md`](./gotxcot-cloud-pipeline.md). Desk seats and tickets: [`desk-operating-model.md`](./desk-operating-model.md). Event envelopes: [`handoff-contracts.md`](./handoff-contracts.md). Gates: [`quality-gates.md`](./quality-gates.md).

---

## 1. Principle — GitHub is the contract of record

| Layer | Role | Not allowed |
|---|---|---|
| **GitHub** (repo, branch, PR, checks, review comments) | **Source of truth** for what shipped, who owns the change, and what may merge | Agents inventing a parallel SoT in chat, Linear-only state, or VPS scratch |
| **Linear** | Planning / tracking overlay (dense GoT issue + CoT sub-issues) | Authoritative merge claim without a matching PR |
| **Notion Agent Task Graph** | Kanban / Graph ID mirror of the same plan | Second work queue that diverges from the PR |
| **Agents** (Cursor Cloud or VPS Hermes) | Execute work packets; land results as commits + PRs + receipts | Chat-paste handoffs as the durable record |

**Rule:** Linear and Notion track *intent and progress*. GitHub records *the change*. LEAD never reports “done” to Ove from tracker state alone — only from PR + receipts + QUALITY (and Greptile when required).

Agents (Cloud or Hermes) **never invent a second SoT**. If Hermes runs on the VPS, its durable output is still a branch/PR on GitHub (plus `.receipts/`), not a private VPS-only artefact.

---

## 2. Runtime lanes

LEAD chooses a lane per ticket (or per Graph node). Default is Lane A unless the ticket/runtime field says otherwise.

```
Ticket / TrackPlan
        │
        ├─ runtime=cloud  (default) ──▶ Lane A: Cursor Cloud Agent
        ├─ runtime=hermes ───────────▶ Lane B: VPS Hermes
        └─ ownership path 1:1 ───────▶ Lane C: Specialist SendToAgent
```

| Lane | When | Who executes | Durable output |
|---|---|---|---|
| **A — Cursor Cloud Agent** | Desk-owned application/code work; default after the **second uplift** | Cloud Agent with the second-uplift XML (`<ISSUES>` nested, live URLs for 5–8 nodes and 4–8 sub-issues each); Notion `Agent` = `cursor-cloud` | Branch + draft PR + `.receipts/` |
| **B — VPS Hermes** | Ticket/runtime says `hermes` — heavy compute, long jobs, Hermes-specific skills/plugins | Hermes on VPS through connected `user-hermes-agent` (`agent_bus_*`; see §5). `handoff_to_hermes` is Hermes-only fallback | Same: branch + draft PR + receipts. Hermes **picks up from GitHub**, not chat paste |
| **C — Specialist 1:1** | Path ownership is clear (`ownership.yaml`); LEAD dispatches concrete tickets | SYSTEMS / WEB / ANDROID / IOS / INFRA / QUALITY via `SendToAgent` | Same GitHub contract; specialist never invents work from channel vibes |

Lanes compose: LEAD may run Lane A/B for a Graph node while Lane C specialists own path slices. Cross-platform features still follow contract-first (`cross-bot-protocol.md`); LEAD integrates.

Lane B does **not** bypass G-1…G-6. Hermes is a runtime, not a second ownership model.

---

## 3. Handoff contract via GitHub

### 3.1 Ticket → branch

Branch naming stays attributable (CI derives acting bot from prefix):

```text
bot-<nn>-<seat>/<task_id>
```

Examples: `bot-02-web-edge/feat-billing-web`, `bot-05-infra/hermes-long-job-cache`.

When a Graph node drives the work, include a short Graph slug or Linear id in `task_id` so PR search and Hermes pickup stay unambiguous.

### 3.2 PR template fields (required for desk PRs)

Authors (Cloud, Hermes, or specialist) fill these in the PR body (and mirror onto Notion Task when sync exists):

| Field | Purpose |
|---|---|
| **Graph ID** | `ut-<base36>-<uuid8>` — idempotent Notion/Linear key |
| **Linear IDs** | Parent issue + relevant sub-issue URLs/ids |
| **Notion URLs** | Task / Issue / Sub-Issue links |
| **runtime** | `cloud` \| `hermes` |
| **owner** | `bot-0N-…` seat id |
| **task_id** | Matches ticket / receipt filename |
| **receipt_path** | `.receipts/<bot-id>/<task_id>.json` |

### 3.3 Work packet (agent-handoff style)

Do **not** rely on chat paste as the handoff. Publish a work packet where Hermes / Cloud / specialists can fetch it from GitHub:

1. **Preferred:** structured block in the **PR description** (or opening issue comment on the PR), plus receipt under `.receipts/`.
2. **Also fine:** `.receipts/<bot>/<task_id>.packet.md` (or JSON) committed on the branch, linked from the PR body.
3. **Pickup:** Hermes (Lane B) watches GitHub — PR labeled / issue comment with `runtime=hermes` and an open draft — **not** Slack/chat blobs.

Minimal packet shape (align with `handoff-contracts.md` envelope ideas):

```markdown
## Work packet
- graph_id: …
- linear: …
- notion: …
- runtime: hermes | cloud
- owner: bot-0N-…
- goal: …
- paths_in_scope: …
- success_criteria: …
- report_back: receipt_path, unverified, blockers
```

### 3.4 Status pipeline

```
draft PR opened
    → Greptile review (MCP trigger + fetch comments)
    → address / waive with receipt
    → QUALITY gate (G-1…G-6 + Greptile checklist)
    → merge
    → sync Linear / Notion from PR fields (LEAD; never invent rows)
    → report to Ove
```

| Stage | Owner | Rule |
|---|---|---|
| Draft PR | Implementing lane | Branch + template fields + receipt path declared |
| Greptile | LEAD / QUALITY via `user-greptile` | Trigger after open; unaddressed comments block merge *claim* |
| QUALITY | bot-06 | Independent review; no self-approval; Greptile status in checklist |
| Merge | Human / protected branch | Required checks including desk gates |
| Sync | LEAD | Mirror PR URL / # / state / checks onto Notion Task + Linear state |
| Report | LEAD | Consolidated receipts + QUALITY verdict; honest `unverified` |

---

## 4. Greptile gate

**MCP:** `user-greptile` (connected). Relevant tools: `trigger_code_review`, `list_code_reviews` / `get_code_review`, `get_merge_request`, `list_merge_request_comments`.

### 4.1 After PR opens

1. Resolve repo tuple via `list_repositories` (`name`, `remote`, `defaultBranch`).
2. Call `trigger_code_review` with that tuple + `prNumber`.
3. Poll `list_code_reviews` / `get_code_review` until status is terminal (`COMPLETED` / `FAILED` / `SKIPPED`).
4. Fetch comments via `get_merge_request` and/or `list_merge_request_comments` (filter Greptile / `addressed`).

A successful trigger means the review was **queued**, not that analysis finished.

### 4.2 Merge claim rule

| Condition | Merge claim |
|---|---|
| Greptile comments with `addressed=false` (unaddressed) | **Block** completion / merge claim |
| Addressed in code + follow-up commit, or waived | Allowed only with a **waiver receipt** |
| Greptile `FAILED` / unavailable | Do not silently skip — record in receipt `unverified` / blocker; LEAD escalates |

**Waiver receipt** (under `.receipts/` or PR comment linked from receipt): who waived, which comment ids, why, and that QUALITY acknowledged. Waiver is reviewable; ignoring Greptile is not.

QUALITY checklist includes Greptile status via `skills/greptile-merge-gate/SKILL.md` (wired into `prompts/bot-06-quality-security.xml` / `QUALITY.xml`). **E2E not verified** — no live trigger on a production PR in authoring; MCP `get_me` returned needsAuth at skill-author time.

---

## 5. Hermes VPS path

### 5.1 Prefer MCP over ad-hoc SSH for code handoffs

| Path | Use for |
|---|---|
| **Hermes MCP** `user-hermes-agent` (HTTP, connected) | Dispatch / status of Hermes work packets. Live Lane B tools are `agent_bus_health`, `agent_bus_start_job`, `agent_bus_get_job`, and `agent_bus_wait_job`. `handoff_to_hermes` is Hermes-only fallback |
| **SSH to VPS** | Infra ops that **INFRA owns** (host, services, non-code ops) — not the default code handoff channel |
| **GitHub PR** | All code work landing place, regardless of runtime |

Today (desk host, 2026-09-24):

- `user-hermes-agent` — **connected** (HTTP). Preferred Lane B path is `agent_bus_*`. `agent_bus_health` returned `status: ok` with runtimes `hermes`, `muse`, `grok-build`, `omp`, `claude-code`. `handoff_to_hermes` stays a Hermes-only fallback; do not use it for a goal that already has an Agent Bus job.
- `user-hermes` (local stdio) — **uninstalled**. Removal on 2026-09-24 was intentional. The server had pointed at a missing `/workspace/hermes-mcp-bridge.mjs`. Agent Bus on `user-hermes-agent` supersedes `hermes-mcp-bridge.mjs`. Do not rebuild the bridge and do not reinstall the stdio server.
- A failed `agent_bus_*` call is a stop. Do not paper over it with chat paste or undocumented SSH for application PRs.

### 5.2 VPS repos (implementation later — not wired as desk SoT today)

Host noted in desk docs: `root@187.77.130.10` (shared root access is a known risk; see README remote-dev note / G-6). Repos observed on that host for **future** Hermes integration work:

| Repo | Likely role (design intent only) |
|---|---|
| `hermes-agent` | Agent runtime |
| `hermes-engineering-board` | Board / orchestration UI or state |
| `hermes-linear-connector` | Linear bridge |
| `hermes-plugin` | Plugin surface |
| `agent-handoff` | Handoff packet conventions |
| `agent-swarm` | Multi-agent coordination |

**Do not claim these repos are wired into Programming Desk LEAD dispatch today.** Lane B dispatch from the desk uses connected `user-hermes-agent`. These host repos are future integration context. GitHub SoT and this doc’s handoff contract stay the desk contract.

### 5.3 Code vs infra

- **Code changes** → branch + PR on the application/repo GitHub remote; Hermes may clone/build on VPS but merge path is GitHub.
- **Infra ops on the VPS** → INFRA ticket + receipts; SSH only under INFRA ownership and G-5/G-6 where applicable.

---

## 6. Gaps / next builds (honest)

| Gap | Why it blocks E2E |
|---|---|
| **Linear MCP** | **Connected 2026-09-24.** Dense smoke SPE-135/SPE-136 on Spectrum Web Co verified and canceled. |
| **Hermes stdio MCP** — `user-hermes` uninstalled 2026-09-24 | **Closed for the missing-bridge blocker.** Do not rebuild `hermes-mcp-bridge.mjs`. Live Lane B is connected `user-hermes-agent` (`agent_bus_*`); `handoff_to_hermes` is Hermes-only fallback. A desk Lane B job that opens a draft PR is still unverified |
| **GoTxCoT double uplift** | **Written** — `skills/gotxcot-uplift/SKILL.md`. First XML uplift, GoT 5–8, sequential CoT 4–8 steps/node, dense kickoff, second uplift with live URLs. VPS engine may still be on MIN_NODES=3 until `vendor/ultrathink-policy/` is applied there. **E2E not verified.** |
| **TrackPlan → CloudAgent / Hermes dispatcher skill** | **Written** — `skills/trackplan-dispatch/SKILL.md`. Consumes the **second-uplift** XML (URLs included) + `runtime`. **E2E not verified.** Lane B uses connected `user-hermes-agent` Agent Bus. Stdio `user-hermes` stays uninstalled. |
| **Greptile in QUALITY checklist** | **Skill written** — `skills/greptile-merge-gate/SKILL.md` + QUALITY prompt checklist. **E2E not verified.** Live MCP calls may need re-auth (`get_me` needsAuth at authoring). |
| **PR → Notion/Linear sync skill** | Mirror after merge (analogue to ultrathink-sync); must not invent tracker rows |
| **VPS Hermes repos** | Present on host; not integrated as desk runtime |

**Do not claim** intake → kickoff → Cloud/Hermes → Greptile → QUALITY → merge → sync works end-to-end until the gaps above are closed and verified with receipts.

---

## 7. Flow (combined with GoTxCoT)

```
Ove ──▶ LEAD intake
           │
           ▼
     First uplift (long nested XML)
           │
           ▼
     GoT 5–8 nodes → CoT sequential, 4–8 steps/node → HITL (≤4)
           │
           ├─▶ Notion Agent Task Graph + Linear dense       [overlays]
           │     (issue/node, sub-issue/step)
           ▼
     Second uplift (same XML + <ISSUES> live URLs)
           │
           ▼
     Choose runtime: cloud (default) | hermes | specialist 1:1
           │
           ▼
     Work packet on GitHub (branch + draft PR + .receipts/)   [SoT]
           │
           ▼
     Greptile → QUALITY (G-1…G-6 + Greptile) → merge
           │
           ▼
     Sync Linear/Notion from PR → report to Ove
```

Upstream planning stays in [`gotxcot-cloud-pipeline.md`](./gotxcot-cloud-pipeline.md). This document owns **runtime lanes**, **GitHub handoff**, **Greptile**, and **Hermes VPS** policy. Node and step clamps are **5–8** and **4–8**.

---

## References

| Path / server | Role |
|---|---|
| `docs/gotxcot-cloud-pipeline.md` | Double uplift, 5–8 nodes, 4–8 sub-issues, dense Linear + Notion |
| `docs/desk-operating-model.md` | Ticket format, SendToAgent |
| `docs/handoff-contracts.md` | Event envelope catalogue |
| `docs/quality-gates.md` | G-1…G-6 |
| `ownership.yaml` | Path → specialist |
| `skills/gotxcot-uplift/SKILL.md` | First uplift through second uplift |
| `skills/trackplan-dispatch/SKILL.md` | Dispatches the second-uplift XML (Lane A/B) |
| `vendor/ultrathink-policy/README.md` | VPS constant/prompt patch (MIN_NODES=5, MIN_STEPS=4) |
| `skills/greptile-merge-gate/SKILL.md` | QUALITY merge-claim Greptile gate |
| MCP `user-greptile` | PR code review trigger + comments |
| MCP `user-hermes-agent` | Lane B control (HTTP, connected). `agent_bus_*` preferred; `handoff_to_hermes` is Hermes-only fallback |
| MCP `user-hermes` | Uninstalled on the desk host 2026-09-24. Do not rebuild `hermes-mcp-bridge.mjs`. Agent Bus supersedes that bridge |
