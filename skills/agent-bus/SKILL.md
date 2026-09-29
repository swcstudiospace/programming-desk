---
name: agent-bus
description: Use when Programming Lead must run a Lane B job on the VPS Agent Bus through the connected HTTP MCP server user-hermes-agent — starting a job with agent_bus_start_job, waiting with agent_bus_wait_job, reading state with agent_bus_get_job, and recording a job id or an honest blocker.
---

# agent-bus

**Owner:** Programming Lead (bot-00). LEAD orchestrates the runtime; specialists own product paths via `ownership.yaml`. Running a bus job never grants the bus, or LEAD, ownership of the paths it edits.

**Scope:** The four `agent_bus_*` tools on connected HTTP MCP `user-hermes-agent`, plus the `handoff_to_hermes` fallback. Control plane reference: `docs/vps-agent-bus.md`.

**Status:** Written for the desk pack. `agent_bus_health` returned `status: ok` on the desk host 2026-09-24. **A desk Lane B job id plus a draft PR is not verified.** Stdio `user-hermes` was intentionally uninstalled on 2026-09-24 — do not rebuild `hermes-mcp-bridge.mjs`.

**Never in a goal, PR, receipt, commit, or chat:** a bus token, a credentialed `wss` URL, or any other secret. Leaking one is a G-3 failure and forces a rotation, which costs more than the job was worth.

---

## When to use / when not

**Use when:**

- `skills/trackplan-dispatch` has selected Lane B (the operator asked, or the ticket `runtime` is a bus runtime), and
- the second-uplift XML with live Notion and Linear URLs exists, and
- a target GitHub repo is known.

**Do not use for:**

- Lane A. Cursor Cloud Agent is the desk default; this skill is not the fallback for a Cloud Agent you did not try.
- Choosing the lane at all — that is `skills/trackplan-dispatch`.
- Creating the uplift, GoT, CoT, or tracker rows — that is `skills/gotxcot-uplift`.
- Claiming merge, QUALITY pass, or Greptile clean.
- Any infra operation on the VPS host. That is an INFRA ticket, not a bus job.

```
Lane B chosen and second-uplift XML has live URLs?
│
├─ NO  ──▶ back to skills/trackplan-dispatch. Do not dispatch a URL-less spec.
│
└─ YES ──▶ agent_bus_health
             │
             ├─ missing / unauthorized / error ──▶ STOP. Blocker in the receipt.
             │                                     No SSH. No stdio rebuild. No raw curl.
             │
             └─ status ok and runtime listed ──▶ §Procedure
```

---

## Procedure

### 1. Health first, every time

Call `agent_bus_health` (no arguments) before any dispatch. Confirm `status` and that the runtime you intend
is in the returned list (`hermes`, `muse`, `grok-build`, `omp`, `claude-code` on 2026-09-24).

Do not trust the recorded snapshot in `docs/vps-agent-bus.md` in place of this call — a runtime that was
present five days ago may be gone, and `agent_bus_start_job` on an absent runtime fails after you have
already told the operator the job was launched.

### 2. Idempotency check before starting

Do not start a job for a `graphId` that may already have one. Check, in order:

1. An existing `jobId` for this `graphId` in `.receipts/bot-00-programming-lead/`.
2. Open GitHub PRs citing the `graphId` or the primary Linear id.
3. A `PR URL` or recorded agent id already on the Notion Task.

If any hit, confirm with the operator before a second launch. If you cannot check, write `unverified` — do
not assume none exist. Two jobs on one goal produce two branches and a merge race that a human has to untangle.

Pass `idempotency_key` on `agent_bus_start_job` whenever re-entry is plausible; key it on `graphId` plus the
node subset so a retry collapses into the original job instead of duplicating it.

### 3. Start the job

`agent_bus_start_job` — required `runtime` and `goal`; optional `provider`, `idempotency_key`. Returns
`jobId`, status, and `wsUrl`.

`goal` carries the **full** GitHub work packet and the second-uplift XML, and the same text goes in the draft
PR body. A paraphrased `goal` means the runtime implements something the PR cannot be reviewed against.

The work packet inside `goal` must state:

- Repo URL, base branch, and that the deliverable is a **branch + draft PR + `.receipts/`** on GitHub.
- `ownership.yaml` binds the runtime: one owner per path, no unowned paths, no cross-seat edits without contract-first (G-1, G-4). Stop with blockers on a conflict rather than editing foreign paths.
- The `<ISSUES>` block is the tracker map — do not open a second set of Linear issues.
- No merge, no Greptile claim.

**`wsUrl` is informational.** MCP does not open the socket, and a public `wss` URL needs a bus token that is
not in the tool result and that the desk does not hold. Record that streaming was not used; do not go looking
for the token.

### 4. Wait, then read

`agent_bus_wait_job` — required `job_id`; timeout default 180s, max 600. Terminal states are `completed`,
`failed`, `error`, or timeout.

**Timeout is not failure.** On timeout call `agent_bus_get_job` (required `job_id`) for the snapshot and, if
the job is still running, wait again on the same `job_id`. Starting a second job because the first timed out
double-spends the runtime and forfeits idempotency.

On `failed` or `error`: record the state and the snapshot tail as a blocker. Do not re-submit blindly — a
second identical job fails the same way and hides the cause.

### 5. Verify on GitHub, not on the bus

A `completed` job is not a delivered job. Confirm the branch and the **draft** PR exist on GitHub before any
report. If there is no PR, that is the finding: report the job id and the absent PR.

### 6. Receipt

Write `.receipts/bot-00-programming-lead/<task_id>.json` per `skills/verification-receipts/SKILL.md` (G-2), with
`lane: "B"`, the runtime used, `agent_id` set to the `jobId` or `null`, each `agent_bus_*` call under `commands`
with its `output_tail`, and `pr_url` only when a PR was actually observed. Honest `unverified` and `blockers`
entries are success.

---

## Fallback: `handoff_to_hermes`

Hermes-only durable EXECUTE fallback, not the multi-runtime path. Required `goal` (string) and `messages`
(array of free-form objects, typically role/content turns). Optional `title`, `priority` (default `normal`),
`labels`, `tenant_id`, `idempotency_key`. The older design-intent shape (`repo`, `branch`, `graph_id`,
`work_packet_markdown`, `prompt` as separate arguments) is **not** live; fold those into `goal` and `messages`.

One handoff per goal. Poll `get_task`. Do not re-submit. **Never call it for a goal that already has an Agent
Bus job** — two runtimes on one goal produce two branches.

---

## Failure modes

| Symptom | Do this | Never do this |
|---|---|---|
| `agent_bus_*` missing or unauthorized | STOP, blocker in the receipt, tell the operator Lane B is blocked | Reinstall stdio `user-hermes`, rebuild `hermes-mcp-bridge.mjs`, or SSH the packet as a code handoff |
| `hermes-mcp-bridge.mjs` not found | Nothing. Its absence is the intended state since 2026-09-24 | Recreate the script — it restores a dead path and masks the real blocker |
| `wsUrl` needs a token | Note that streaming was unused; poll instead | Hunt for, invent, or paste a token (G-3) |
| `agent_bus_wait_job` times out | `agent_bus_get_job`, then wait again on the same `job_id` | Start a second job |
| Job `completed`, no PR on GitHub | Report the job id and the missing PR as the outcome | Report "done", or write a `pr_url` that was not observed |
| Runtime absent from `agent_bus_health` | Blocker, or pick a listed runtime the operator approves | Start the job anyway and announce a launch |
| Bus edited paths across seats | Blocker per G-1; contract-first per G-4 | Accept the diff because "the bus did it" |

## Worked examples

**Good.** `agent_bus_health` → `status: ok`, `hermes` listed. No prior `jobId` for `ut-abc123-…` in receipts,
no open PR citing it. `agent_bus_start_job` with `runtime: hermes`, full work packet plus second-uplift XML in
`goal`, `idempotency_key` keyed on the graph id. Returns `jobId` and a `wsUrl` — socket not opened, noted as
unused. `agent_bus_wait_job` times out at 180s → `agent_bus_get_job` shows `running` → wait again → `completed`.
Draft PR confirmed on GitHub. Receipt lists all five calls, `agent_id` = `jobId`, `pr_url` set,
`unverified: ["Greptile not run (QUALITY)"]`.

**Bad.** `agent_bus_health` returns unauthorized. LEAD SSHes the VPS, clones the repo, commits from the host,
and reports the work landed. Three failures in one turn: the blocker was hidden, GitHub stopped being the
source of truth, and no gate ran on the diff. The correct turn ends with a blocker and no code.

---

## References

| Path | Role |
|---|---|
| `docs/vps-agent-bus.md` | Control plane: tools, endpoints, stop rules, honest gaps |
| `skills/trackplan-dispatch/SKILL.md` | Lane selection, work packet, dispatch receipt shape |
| `skills/gotxcot-uplift/SKILL.md` | Produces the second-uplift XML |
| `docs/github-sot-orchestration.md` | Lanes, GitHub source of truth, §5 Hermes VPS policy |
| `skills/verification-receipts/SKILL.md` | G-2 receipt rules |
| `docs/quality-gates.md` | G-1 ownership, G-2 receipts, G-3 secrets, G-4 contract-first |
| `ownership.yaml` | `skills/agent-bus/**` → bot-00 |
