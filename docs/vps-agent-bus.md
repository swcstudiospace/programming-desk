# VPS Agent Bus — Lane B control plane

**Owner:** Programming Lead (bot-00) per `ownership.yaml`. LEAD orchestrates dispatch; it does not own product code.
**Audience:** LEAD dispatching Lane B work, and any reviewer checking a Lane B claim.
**Recorded:** 2026-09-24 desk-host observation, written up 2026-09-29 (Sydney).
**Status:** Control-plane reference. `user-hermes-agent` is **connected** and `agent_bus_health` returned `status: ok`. A desk Lane B job that lands a draft PR is **not verified** end to end (see [Honest gaps](#honest-gaps)). Nothing in this document proves a job id.

Companions: lanes and GitHub source of truth in [`github-sot-orchestration.md`](./github-sot-orchestration.md) §5. Dispatch procedure in [`../skills/agent-bus/SKILL.md`](../skills/agent-bus/SKILL.md) and [`../skills/trackplan-dispatch/SKILL.md`](../skills/trackplan-dispatch/SKILL.md). Receipts in [`../skills/verification-receipts/SKILL.md`](../skills/verification-receipts/SKILL.md).

---

## 1. What the Agent Bus is

`vps-agent-bus` is an HTTP job service running on the INFRA-owned VPS (host recorded in
[`github-sot-orchestration.md`](./github-sot-orchestration.md) §5.2 — not repeated here). It accepts a
goal plus a runtime name, queues a job, and exposes job state. The desk reaches it **only** through the
connected HTTP MCP server `user-hermes-agent`, which wraps the bus endpoints as `agent_bus_*` tools.

| Layer | What it is | Desk access |
|---|---|---|
| `vps-agent-bus` HTTP API | `POST /v1/jobs`, `GET /v1/jobs/{id}`, loopback health | **Not called directly by LEAD.** No raw curl, no SSH |
| MCP server `user-hermes-agent` | HTTP MCP wrapper, connected on the desk host | The only desk path. Call `agent_bus_*` |
| Runtimes behind the bus | `hermes`, `muse`, `grok-build`, `omp`, `claude-code` (as reported by `agent_bus_health` on 2026-09-24) | Selected by the `runtime` argument |
| GitHub | Branch, draft PR, checks | **Source of truth.** The bus computes; GitHub records |

**The bus is a computer, not a source of truth.** A completed job with no branch and no draft PR has
produced nothing the desk can report, because there is no reviewable artefact and no gate ran.

### What is deliberately absent

Local stdio MCP `user-hermes` was **uninstalled on purpose** on the desk host on 2026-09-24. It pointed at a
missing `/workspace/hermes-mcp-bridge.mjs`. Agent Bus on `user-hermes-agent` supersedes that bridge.

- Do **not** reinstall the stdio server.
- Do **not** recreate `hermes-mcp-bridge.mjs`. Its absence is the intended state, not a broken install to repair.
- Do **not** read "stdio missing" as "Lane B is down". Lane B is the HTTP path above.

---

## 2. Live MCP tools

Four tools on `user-hermes-agent`. Names and arguments as observed; if a live schema disagrees with this
table, the live schema wins and this document is the thing to fix.

| Tool | Underlying call | Returns | Arguments |
|---|---|---|---|
| `agent_bus_health` | loopback health | `status` and the available runtimes | none |
| `agent_bus_start_job` | `POST /v1/jobs` | `jobId`, status, `wsUrl` | required `runtime`, `goal`; optional `provider`, `idempotency_key` |
| `agent_bus_get_job` | `GET /v1/jobs/{id}` | one job snapshot | required `job_id` |
| `agent_bus_wait_job` | polls the snapshot | terminal state or timeout | required `job_id`; timeout default 180s, max 600 |

Terminal states from `agent_bus_wait_job`: `completed`, `failed`, `error`, or timeout. **Timeout is not
failure** — the job may still be running, so re-check with `agent_bus_get_job` rather than starting a
second job, which would double-spend the runtime on one goal.

### `wsUrl` and the WebSocket

`agent_bus_start_job` returns a `wsUrl` for streaming, and **MCP does not open that socket**. A public
`wss` URL needs a bus token that the desk does not hold and that is not part of the tool result.

- Do not write a token, header value, or credential into a `goal`, a PR body, a receipt, a commit message, or chat.
- Do not treat a missing token as a reason to try SSH, a raw HTTP call, or any other side channel.
- Without the socket, `agent_bus_get_job` and `agent_bus_wait_job` are the supported status path. They are sufficient.

### Fallback: `handoff_to_hermes`

`handoff_to_hermes` is the **Hermes-only durable EXECUTE fallback**, not the multi-runtime path. Use it for
one durable Hermes EXECUTE when `agent_bus_*` is not the right shape, poll `get_task`, and do not re-submit.

Live schema: required `goal` (string) and `messages` (array of free-form objects, typically role/content turns).
Optional `title`, `priority` (default `normal`), `labels`, `tenant_id`, `idempotency_key`. The older
design-intent shape (`repo`, `branch`, `graph_id`, `work_packet_markdown`, `prompt` as separate arguments) is
**not** live; fold those into `goal` and `messages`.

**Never fire `handoff_to_hermes` for a goal that already has an Agent Bus job.** Two runtimes working one goal
produce two branches and a merge race.

---

## 3. Dispatch sequence

```
Second-uplift XML (live Notion + Linear URLs) + runtime=hermes/bus runtime
│
├─▶ agent_bus_health          → status ok? runtime present in the list?
│        │
│        └─ no / unauthorized / error ──▶ STOP. Record blocker. No SSH, no stdio rebuild.
│
├─▶ idempotency check         → existing job or open PR for this graphId? → confirm with operator first
│
├─▶ agent_bus_start_job       → jobId  (runtime + goal; idempotency_key when re-entry is plausible)
│
├─▶ agent_bus_wait_job        → completed | failed | error | timeout
│        └─ timeout ──▶ agent_bus_get_job. Do NOT start a second job.
│
└─▶ Verify on GitHub          → branch + draft PR exist?  → receipt
         └─ no PR ──▶ the job did not deliver. Report that, do not report "done".
```

`goal` carries the GitHub work packet and the second-uplift XML, and the same text goes in the draft PR body so
the spec and the artefact cannot drift.

---

## 4. Blockers and the stop rule

A missing, unauthorized, or erroring `agent_bus_*` call is a **stop**, recorded as a blocker in the LEAD receipt.
It is never grounds for any of the following:

| Forbidden substitution | Why |
|---|---|
| SSH the packet as a code handoff | Bypasses GitHub as source of truth and every gate G-1…G-6. INFRA owns SSH for ops, not as a secret code path |
| Rebuild `hermes-mcp-bridge.mjs` / reinstall stdio `user-hermes` | Removal was intentional; rebuilding restores a dead path and hides the real blocker |
| Raw `curl` at the bus API or a hand-made WebSocket | Needs a credential the desk does not hold. Fabricating one is a secret-handling incident (G-3) |
| Paste the packet into chat as the durable record | Chat is not an artefact. Nothing can be reviewed or merged from it |
| Claim pickup with no `jobId` and no draft PR | An unevidenced claim. PD-1/PD-6: say what was not run |
| Start a second job for the same goal | Duplicate branches, duplicate tracker state, merge race |

---

## 5. Receipt fields

Lane B dispatch writes `.receipts/bot-00-programming-lead/<task_id>.json` per
[`../skills/verification-receipts/SKILL.md`](../skills/verification-receipts/SKILL.md), with `lane: "B"`,
`runtime: "hermes"` (or the bus runtime used), `agent_id` set to the `jobId` or `null`, and the
`agent_bus_*` calls listed under `commands` with their `output_tail`.

What belongs in `unverified` rather than in a claim:

- `pr_url` when no draft PR has been observed on GitHub.
- Greptile — QUALITY runs it, not LEAD.
- Job completion when `agent_bus_wait_job` timed out instead of reaching a terminal state.

What must never appear anywhere in a receipt: a bus token, a `wss` URL carrying a credential, or any other secret.

---

## Honest gaps

| Gap | State |
|---|---|
| Lane B E2E | `user-hermes-agent` is connected and `agent_bus_*` is the live path. **No desk job id plus draft PR has been recorded.** This document does not prove one |
| Health snapshot age | `status: ok` and the runtime list are the 2026-09-24 observation. Re-run `agent_bus_health` before dispatch rather than trusting this table |
| `wsUrl` streaming | Never exercised from the desk. Token-gated and out of desk scope |
| Bus API surface | Only the endpoints the four MCP tools wrap are documented. Anything else on `vps-agent-bus` is undocumented here on purpose |
| VPS Hermes repos | Present on the host (`github-sot-orchestration.md` §5.2), not wired as desk runtime |

---

## References

| Path | Role |
|---|---|
| `skills/agent-bus/SKILL.md` | Dispatch procedure for these tools |
| `skills/trackplan-dispatch/SKILL.md` | Lane selection and the work packet this bus consumes |
| `docs/github-sot-orchestration.md` | Lanes, GitHub source of truth, §5 Hermes VPS policy |
| `docs/intake-e2e-runbook.md` | Operator intake path that reaches dispatch |
| `skills/verification-receipts/SKILL.md` | G-2 receipt rules |
| `ownership.yaml` | `docs/vps-agent-bus.md` and `skills/agent-bus/**` → bot-00 |
