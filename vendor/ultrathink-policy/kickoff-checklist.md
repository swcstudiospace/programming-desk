# Kickoff checklist (desk copy)

Upstream skill: `claude-ultrathink/skills/ultrathink-kickoff/SKILL.md` on the VPS.
This file is the Programming Desk override. LEAD follows it from `skills/gotxcot-uplift`
after GoT and per-node CoT exist, and **before** the second uplift.

Do not start specialist implementation in this checklist. Materialize trackers, then
second-uplift, then `skills/trackplan-dispatch`.

## Overrides vs stock kickoff

| Stock | Desk |
|---|---|
| CoT steps described as 5–8 | **4–8** steps, each a Sub-Issue |
| GoT often 3–8 | **5–8** nodes, each an Issue |
| Task `Agent` = `claude-code` | **`cursor-cloud`** when Lane A executes |
| Final prompt = reprint XML + trailing `<ISSUES>` | That emission is the **input** to the second uplift, which nests `<ISSUES>` inside the root |
| Then Claude Code `Task` subagents | Then Cursor Cloud Agent (default) or Hermes |

## 0. State

You need a plan shape equivalent to upstream `SessionRecord.plan`:

- `graphId` — `ut-<base36>-<uuid8>`
- `task` — item, description, uplifted prompt (may be truncated to ~1900 chars in Notion; full XML stays in the packet)
- `issues[]` — one per node (`graphId`, `nodeId`, `item`, `thought`)
- `subIssues[]` — several per `nodeId`, one per rationale step (`step` 1-based)
- `linearIssues[]` / `linearSubIssues[]` — titles and bodies for Linear
- `hitl` — blocking (≤4) and non-blocking clarifications

If tracking cannot be built, say so, skip row creation, and do **not** invent URLs in the second uplift. Dispatch may still proceed only if the operator explicitly accepts a tracker-less run; record that in the Lead receipt `unverified`.

## 1. Find or create the Notion Task

Collection: `collection://be3418f0-d2d8-411b-8677-fa8a95ee63be` (🧩 Agent Task Graph).

Query `Graph ID` = `plan.graphId`. Re-entrant kickoff **updates**; it does not duplicate the Task.

## 2. Task properties

| Notion property | Value |
|---|---|
| `Item` | task title |
| `Level` | `Task` |
| `Description` | task description |
| `Uplifted Prompt` | truncated first-uplift XML |
| `Agent` | **`cursor-cloud`** for Lane A (not `claude-code`) |
| `Status` | `Planning` until step 6, then `Implementing` |
| `Linear State` | `Todo` |
| `Repo` / `Branch` | when known |
| `Graph ID` | idempotency key |
| `Started` | now, only on first create |

## 3. One Linear issue + one Notion Issue per node

Team: **Spectrum Web Co**.

For every node (5–8):

1. Create the Linear **issue** (`title` = node title, `description` = conclusion or question).
2. Create or update the Notion **Issue**: `Parent Item` = Task, `Item` = `[nodeId] Title`, `Graph ID`, `Linear URL`, `Issue ID`, `Issue Type` from kind (`understand` / `decompose` / `compare` / `critique` → Investigation; `generate` / `refine` / `synthesize` → Feature).

## 4. One Linear sub-issue + one Notion Sub-Issue per step

For every step on every node (4–8 steps each):

1. Create the Linear **sub-issue** under that node’s issue. Title: `"{node title} — Step N: {snippet}"`. Body: full step text.
2. Create or update the Notion **Sub-Issue**. `Parent Item` = the **Issue** page, not the Task. Set `Step`, `Thought`, `Graph ID`, `Linear URL`.

Batch per node when the tools allow. If one create fails, continue and record `nodeId` + `step`. Never stop after step 1.

## 5. HITL

- Non-blocking: take the default and state it.
- Blocking: at most 4, asked together. If no operator is available, take defaults and say so.
- Carry answers into `<CLARIFICATIONS>` on the second uplift.

## 6. Hand off to the second uplift

Set Task `Status` to `Implementing` only when dispatch is about to happen.

Emit the URL map (Task, every Issue, every Sub-Issue). The second uplift in
`skills/gotxcot-uplift` consumes that map. Do not treat the stock trailing `<ISSUES>`
block as the final prompt if it sits outside the root or omits URLs.

## 7. Do not execute product code here

Stock kickoff step 7 says to start coding with Claude Code subagents. On this desk,
step 7 is **dispatch** via `skills/trackplan-dispatch`, or specialist tickets via
`SendToAgent` when ownership is already 1:1. LEAD does not edit product paths.
