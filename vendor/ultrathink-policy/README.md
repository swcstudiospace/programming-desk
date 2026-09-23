# Ultrathink engine patch (VPS `claude-ultrathink`)

The Graph-of-Thought engine is **not** in this GitHub repository. It lives on the VPS
(typically `/root/src/repos/claude-ultrathink`). This directory is the desk policy the VPS
copy should be patched to. Do not clone or push a second ultrathink repo from here.

Desk skills (`skills/gotxcot-uplift`, `skills/trackplan-dispatch`) already follow these
numbers. Until the VPS files change, a Claude Code hook on that host can still emit a
3-node graph or a "4 to 8 nodes" prompt. LEAD must clamp to this policy anyway.

Constants the desk runs with: [`constants.ts`](./constants.ts).  
Kickoff checklist (desk overrides of `ultrathink-kickoff`): [`kickoff-checklist.md`](./kickoff-checklist.md).

---

## Exact upstream diffs

Apply on the VPS tree. Paths are relative to `claude-ultrathink/`.

### 1. `src/think/types.ts` — node and step clamps

```diff
-export const MIN_NODES = 3;
+export const MIN_NODES = 5;
 export const MAX_NODES = 8;

-/** Numbered rationale steps the CoT fill must produce per node; each step becomes one Sub-Issue. */
-export const MIN_STEPS = 5;
+/** Numbered rationale steps the CoT fill must produce per node; each step becomes one Sub-Issue. */
+export const MIN_STEPS = 4;
 export const MAX_STEPS = 8;
```

`MAX_NODES` stays **8**. `MAX_STEPS` stays **8**. `MAX_RATIONALE_CHARS` stays **2000**.

`FALLBACK_GRAPH` already has five nodes (`n1`–`n5`). Leave it. It satisfies the new minimum.

### 2. `src/think/prompts.ts` — GoT system prompt string

`GRAPH_SYSTEM_PROMPT` still says the graph has 4 to 8 nodes. Replace that rule line exactly:

```diff
 Rules:
-- 4 to 8 nodes.
+- 5 to 8 nodes.
 - First node: kind "understand", depends_on [].
```

Do not leave both sentences. The model follows the prompt text, not only `MIN_NODES`.

`COT_SYSTEM_PROMPT` interpolates `` `${MIN_STEPS} to ${MAX_STEPS}` ``. After the types.ts
change it reads **4 to 8** numbered steps with no further string edit. Confirm the rendered
prompt no longer says "5 to 8" unless you intentionally kept `MIN_STEPS = 5` (the desk does not).

### 3. `src/think/pipeline.ts` — sequential CoT fill

No numeric change required. `runThink` already does:

```ts
const concurrency = Math.max(1, Math.floor(opts.concurrency ?? 1));
```

and, when `concurrency === 1`, fills nodes in a `for` loop (one node at a time).

**Desk preference:** leave the default at **1**. Do not change the default to "fill the level
in parallel". Parallel fill stays available when a caller passes `concurrency > 1` **and**
the runtime can do it without tripping rate limits. Document that call site; do not flip the
default.

`normalizeGraph(..., minNodes, maxNodes)` must receive `minNodes = 5` via the new `MIN_NODES`.
Reject or regenerate graphs shorter than 5 for a real build task rather than padding with
empty nodes.

### 4. `src/config.ts` defaults (if present)

```diff
-  "think": { "minNodes": 3, "maxNodes": 8, "engine": "claude" },
+  "think": { "minNodes": 5, "maxNodes": 8, "engine": "claude" },
```

Local `~/.claude/ultrathink.json` / `<project>/.claude/ultrathink.json` overrides must not
silently set `minNodes` back to 3 on Programming Desk hosts.

### 5. `skills/ultrathink-kickoff/SKILL.md` — step counts in prose

The kickoff skill text says each node's rationale is **5–8** steps and the `<ISSUES>` comment
says "5-8 per node". After `MIN_STEPS = 4` those sentences are wrong.

```diff
-Each node's Chain-of-Thought fill is a numbered rationale of 5-8 steps, and **every step is its own Sub-Issue**.
+Each node's Chain-of-Thought fill is a numbered rationale of 4-8 steps, and **every step is its own Sub-Issue**.
```

```diff
-	<!-- one ISSUE per graph node, one SUBISSUE per rationale step (5-8 per node) -->
+	<!-- one ISSUE per graph node, one SUBISSUE per rationale step (4-8 per node) -->
```

Also set the Task `Agent` property to **`cursor-cloud`** when the executor is a Cursor Cloud
Agent. Stock kickoff writes `plan.task.agent` (`"claude-code"`). Desk kickoff must pass
`cursor-cloud` into `plan.task.agent` for Lane A. Do not hard-code `claude-code` in the skill
table for Programming Desk runs.

### 6. Second uplift — not in the engine today

Upstream kickoff step 6 **reprints** `plan.task.upliftedPrompt` and **appends** an `<ISSUES>`
block. That is one emission, not a second rewrite.

Desk policy (`skills/gotxcot-uplift`) adds a **second uplift**: rewrite/extend the already
uplifted XML so `<ISSUES>` is a child of the root and every Task / Issue / Sub-Issue carries
live Notion and Linear URLs. The result must stay long and tag-dense.

There is no `injectIssues` function in the uploaded `pipeline.ts`. Optional later VPS addition
(do not pretend it exists until it lands):

- Input: first-uplift XML + the URL map from kickoff.
- Output: the same root, with `<ISSUES>` and `<CLARIFICATIONS>` nested inside it, ORIGINAL unchanged.
- Must not call Linear or Notion again (idempotency stays in kickoff).

Until that function exists, LEAD performs the second uplift in the desk skill and dispatches
**that** document via `skills/trackplan-dispatch`.

---

## What not to change

- Do not drop Dense for the OMP compact skill. Compact stays a quota fallback.
- Do not lower `MAX_NODES` or raise it above 8.
- Do not collapse CoT steps into one Linear issue per node.
- Do not point Notion `Agent` at `claude-code` for Cursor Cloud Agent runs.
- Do not weaken Greptile or gates G-1…G-6 from this patch.

---

## Verify after patching the VPS copy

1. `MIN_NODES === 5`, `MAX_NODES === 8`, `MIN_STEPS === 4`, `MAX_STEPS === 8`.
2. `GRAPH_SYSTEM_PROMPT` contains the line `- 5 to 8 nodes.` and does not contain `- 4 to 8 nodes.`
3. A dry GoT on a non-trivial prompt returns between 5 and 8 nodes.
4. A dry CoT on one node returns between 4 and 8 numbered steps.
5. Default `runThink` still fills nodes one at a time.
6. Kickoff prose says 4–8 sub-issues per node, and Desk Tasks get `Agent = cursor-cloud`.

This repository cannot run that dry check. Do not mark it done from here.
