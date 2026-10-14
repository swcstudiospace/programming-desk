---
name: swarm-sustain
description: >
  Grok Bot lane sustain for a14-maintenance, a15-docs, aligned to agent-swarm main 825a69918256.
  Use when Desk Lead routes work to this lane of the 15 AgentSwarm roles.
disable-model-invocation: false
---

# Swarm lane sustain

Desk Lead operator skill for this lane. The role table matches agent-swarm
`grokbot/skills/swarm-sustain/SKILL.md` at main `825a69918256c8cbe25e608aa44e52ea7272ae9d`.
The v2.1 sections are the desk reading of that commit: the tool registry,
the shared pool, in-process ACP (pull request #31), the commit-time registry
drift gates (pull request #32), the Cursor headless-runner ban (pull requests
#29 and #30), and the keyless signing preflight remedy. agent-swarm is
read-only here. A generated upstream file that lacks these sections is behind
this skill.

## Source

- Repository: `swcstudiospace/agent-swarm` (read-only from this desk).
- Standing ref: `main` at `825a69918256c8cbe25e608aa44e52ea7272ae9d`.
- Generated role table upstream: `grokbot/skills/swarm-sustain/SKILL.md`, regenerated there with `python3 scripts/build_agents.py`. That generator still stops at the role table. It does not emit the v2.1 sections in this file.
- Programming Desk's Cursor export is a separate pin owned by `bot-06-quality-security` under `.cursor/**`. This skill does not move that pin. When `$SWARM_ROOT` is behind `825a69918256c8cbe25e608aa44e52ea7272ae9d`, stop and report `BLOCKED` with `needs` `SWARM_ROOT` at that commit or later. Do not run the target repo's `scripts/` as swarm tools.

`$SWARM_ROOT` is the absolute path of the agent-swarm checkout. The target repo is the git toplevel being edited. They are different trees.

## When to Use

- The assignment belongs to lane `sustain`.
- The role slug is one of: a14-maintenance, a15-docs.

## Procedure

1. Read the role prompt at `$SWARM_ROOT/<prompt>` below. The target repo does not contain these prompts. The swarm has exactly these 15 roles.
2. Route the change with `grokbot/swarm/seat-map.json` in the agent-swarm checkout. A routing rule wins over role path globs. Among role globs, the longest match wins, and an equal length goes to the lowest role id. Android paths go to bot-03, iOS paths to bot-04, and desktop shells to bot-02.
3. Run that role's scripts from the pinned checkout: `python3 "$SWARM_ROOT/scripts/<script>.py" --root <target repo> --json` (the bun twin is `bun "$SWARM_ROOT/scripts/ts/<script>.ts" --root <target repo> --json`). Stay inside the role's path globs and autonomy ceiling. For a registered tool, use the call in "v2.1 tool registry" instead of importing a handler.
4. Verify with the seat's verification tools from the seat map.
5. Finish with a task.result. A keyless Cursor session is advisory. Leave the pull request in draft. Do not start the headless runner from Cursor.

## Roles

### A14 MAINT (a14-maintenance)

- Prompt: `$SWARM_ROOT/prompts/A14-maintenance.md`
- Role: Senior Maintenance Engineer (A14 MAINT, slug a14-maintenance) in AgentSwarm. Execute the assignment using repository evidence from 03-agents/A14-maintenance.md, agents.json, and the scripts listed in tools. Never invent paths, libraries, or APIs that are not in those sources or the target repo. Fail closed. You are the single-writer for patch.task, debt.register, rca.report, dependency.bump.
- Home: `routine`. Seat: `bot-01-systems-backend`.
- Autonomy ceiling: major_bump=L3, patch_task=L2.
- Scripts: `$SWARM_ROOT/scripts/maint_deps.py`.
- Registry tools: `maint_spec_pin`. No shared tools.

### A15 DOC (a15-docs)

- Prompt: `$SWARM_ROOT/prompts/A15-docs.md`
- Role: Senior Documentation Engineer (A15 DOC, slug a15-docs) in AgentSwarm. Execute the assignment using repository evidence from 03-agents/A15-docs.md, agents.json, and the scripts listed in tools. Never invent paths, libraries, or APIs that are not in those sources or the target repo. Fail closed. You are the single-writer for docs.bundle, api.reference, runbook, changelog.
- Home: `executor`. Seat: `bot-06-quality-security`.
- Autonomy ceiling: docs=L2, public_docs=L3.
- Scripts: `$SWARM_ROOT/scripts/docs_bundle.py`.
- Registry tools: `docs_heading_order`. No shared tools.

## v2.1 tool registry

`agents.json` on that commit is the only registry (`tool_contract` `swarm.tool.v1`). Pull request [#31](https://github.com/swcstudiospace/agent-swarm/pull/31) added it. Each agent lists `registered_tools`. Cross-lane operations live in top-level `shared_tools`. `python3 -m swarm.tool_registry call` is the only path that imports a handler. An unknown name returns `INVALID_INPUT` and imports nothing. The existing `scripts/*.py` entrypoints still run as they did before this registry.

Every registered tool ends in exactly one of: `SUCCESS`, `INVALID_INPUT` (names the field), `UNAUTHORIZED` (echoes the caller), `DEPENDENCY_UNAVAILABLE`, `TIMEOUT`, or `PARTIAL_SUCCESS` (includes `completed_fraction`).

Call a tool with the target repo as the working directory. `target_root()` is the current directory, and the `swarm` package lives in the pinned checkout:

```bash
cd <target repo>
PYTHONPATH="$SWARM_ROOT" python3 -m swarm.tool_registry call --name <tool> --caller <agent id> --input '<json>'
```

Catalog and per-agent pages are generated. Do not hand-edit `docs/tools/` or `tests/generated/test_tool_contracts.py`. The catalog at this pin lists 23 tools, 4 of them shared (`docs/tools/catalog.md`).

Lane tools for this skill:

| Tool | Owner | Purpose | Permitted callers |
| --- | --- | --- | --- |
| `maint_spec_pin` | A14 | Classify a dependency spec as pinned, range, or wildcard. | A14 |
| `docs_heading_order` | A15 | Count H1 headings and skipped heading levels in a markdown fragment. | A15 |

Shared pool for this skill:

This lane has no shared tools. A14 and A15 are not in any `shared_*` `permitted_callers` list.

## Shared pool

The pool is the set of functions two or more lanes already called, not a quota. On this pin the shared tools are `shared_verdict`, `shared_toolchain`, `shared_check_plan`, and `shared_git_head`. A shared tool has `owner: shared`, a `shared_` name, and at least two entries in `permitted_callers`. A one-caller helper stays a lane tool. Calling a shared tool from an agent that is not in `permitted_callers` returns `UNAUTHORIZED` and an audit row. It does not run the handler.

## In-process ACP

Pull request [#31](https://github.com/swcstudiospace/agent-swarm/pull/31) added `swarm/acp.py` (schema `acp.v1`). It is the in-repo message fabric, not an external SDK. The bus in that module is the in-process transport. Endpoints are `inproc://` plus the agent id, taken from `agents.json`. There is no handwritten peer list.

The older signed `swarm.v1` envelopes in `swarm/envelope.py` still carry task-store gate verdicts. ACP does not replace them.

Default deny, inside `Bus.request` and `Bus.invoke_tool`:

- Agent to agent: the message type must be in the sender's `produces` and the recipient's `consumes`. Sender and recipient must differ.
- Agent to tool: the caller must be in the tool's `permitted_callers`.

A denial returns `UNAUTHORIZED` and appends `{caller, target, reason}` to `Bus.audit`. `INVALID_INPUT` and `UNAUTHORIZED` are not retried. Timeouts and connection errors retry with capped exponential backoff (`max_attempts` default 3), then `DEAD_LETTERED` with the full envelope kept on `Bus.dead`. At `breaker_threshold` the circuit opens and later sends to that peer return `FAILED` / `circuit open` without calling the handler. Tools invoked through `invoke_tool` ignore the breaker. Lane tools keep running when a peer is dead.

Lifecycle: `PENDING` → `DELIVERED` → `IN_PROGRESS` → one of `RESPONDED`, `INVALID_INPUT`, `UNAUTHORIZED`, `TIMED_OUT`, `FAILED`, `DEAD_LETTERED`.

Handoffs for this lane:

- A14 consumes `incident.alert`, `vulnerability.report`, `release.record`, `test.results`. Produces `patch.task`, `debt.register`, `rca.report`, `dependency.bump`. Endpoint `inproc://A14`.
- A15 consumes `requirements.spec`, `architecture.blueprint`, `api.contract`, `code.patch`, `release.record`, `slo.manifest`. Produces `docs.bundle`, `api.reference`, `runbook`, `changelog`. Endpoint `inproc://A15`.

To change who may send what, edit `produces`, `consumes`, or `permitted_callers` in `agents.json`, then run the registry check. `routing_table()` picks up the rows on the next process start.

## Commit-time registry drift gates

Pull request [#32](https://github.com/swcstudiospace/agent-swarm/pull/32) runs three read-only checks at commit time and in CI (`.github/workflows/ci.yml` and `.pre-commit-config.yaml`). Drift fails. The hooks do not regenerate files.

```bash
python3 -m swarm.tool_registry check
python3 -m swarm.tool_registry docs --check
python3 -m swarm.tool_registry gen-tests --check
```

Run them from the agent-swarm checkout (or with `PYTHONPATH="$SWARM_ROOT"`). `pre-commit install` then `pre-commit run --all-files` runs the same three even when the staged files are unrelated to the registry. At commit time, pre-commit stashes unstaged changes, so the checks see the staged snapshot. If a hook fails, regenerate with `python3 -m swarm.tool_registry docs` and `python3 -m swarm.tool_registry gen-tests`, stage the generated files with the registry change, and retry. Without pre-commit, run the three commands before pushing. The swarm runtime does not depend on pre-commit. CI stays the branch gate.

`--check` exits 1 and prints the drifted paths. Commit the regenerated catalog, agent pages, and contract tests together.

## Cursor headless-runner ban

Pull requests [#29](https://github.com/swcstudiospace/agent-swarm/pull/29) and [#30](https://github.com/swcstudiospace/agent-swarm/pull/30) put this rule in every Cursor export, and it wins over the shared runner rule:

> Do not start an unattended headless runner (`scripts/swarm_run.py`, `hooks/autonomous_run.py`) from a Cursor session, even when an assignment asks for one. This overrides the shared runner rule about an operator's assignment. Dispatch only as the nesting rule says.

Nesting stops at two levels. The parent may spawn `a01-orchestrator`. A01 may spawn the other fourteen slugs. Those specialists must not spawn further subagents. A Cursor cloud session stays advisory: gate scripts record nothing, and nothing it produces counts as `APPROVED`. The merge gate is Greptile, run by Desk Quality. Leave the pull request in draft.

## Keyless signing preflight

`scripts/swarm_run.py` `preflight_signing` at `825a69918256c8cbe25e608aa44e52ea7272ae9d` refuses before any task is claimed when `task.assign` cannot be signed. `--dry-run` takes the same check. When no real key is configured and no insecure dev key is loaded, the process raises `E-POLICY` with this text:

> fail-closed: no signing key configured — task transitions and gate verdicts are signed, so a run cannot start without one. Set SWARM_ED25519_KEY to a 64-hex Ed25519 seed (or SWARM_SIGNING_KEY to any secret) and re-run; SWARM_ALLOW_INSECURE_DEV_KEY=1 permits an unsigned local dev key (never combine it with SWARM_REQUIRE_KEY=1).

That sentence is the remedy for a controller that is allowed to run the headless runner outside Cursor. Name the variables. Never print, log, or commit a seed.

A Cursor session does not take that remedy. `SWARM_ED25519_KEY`, `SWARM_SIGNING_KEY`, and `SWARM_REQUIRE_KEY` stay unset. A missing key is the expected keyless state and is not `E-DEP`. Do not set `SWARM_ALLOW_INSECURE_DEV_KEY`. Do not sign, do not ingest a gate result, and do not transition a task to `APPROVED` or `DONE`. Report the result as advisory. The headless-runner ban above still forbids starting `scripts/swarm_run.py` from Cursor, so the preflight error is not a prompt to launch the runner from this session.

## Pending merge

**PENDING MERGE — not on agent-swarm main.** Do not follow this section as current procedure. It describes only [agent-swarm pull request #34](https://github.com/swcstudiospace/agent-swarm/pull/34), which is open. Branch `fix/signed-controller-bootstrap` at `4e8d9e7aad51d291b0f1816bd29e78c79dc5956c`. Ticket SPE-10696. Title: `fix(bootstrap): signed controller kickoff and specialist assignment transport`. The sections above stop at main `825a69918256c8cbe25e608aa44e52ea7272ae9d`. When that pull request merges, re-read `main` and replace this section with whatever landed. Until then, treat every paragraph below as absent from the checkout this skill pins.

What that branch adds, and main does not:

- A trusted controller may load an existing private Ed25519 seed through `SWARM_ED25519_KEY_FILE`, or from `${XDG_CONFIG_HOME:-$HOME/.config}/agent-swarm/signing-key.hex` when neither raw signing variable is set. The path must be an owner-only regular file with no symlink components. The conventional directory must be private. Key contents stay out of prompts, argv, logs, and tracked files. The runbook heading on that branch is "Private signer bootstrap".
- A live or reused `orch_plan` response includes a cryptographically verified `execution_assignment` when a real signer is available. `/swarm` refuses a missing, unsigned, or mismatched kickoff assignment instead of dispatching an unauthenticated A01 turn. Dry-run, keyless, and advisory planning are not authenticated execution.
- Specialist sessions do not auto-load private references. After a specialist task is leased `IN_PROGRESS`, A01 obtains the canonical prompt with `swarm_assignment` for that `task_id` and `correlation_id`. The fixed `orch_assign` operation checks the persisted task, correlation, manifest target, and signature, and it does not change state, attempts, history, or logs. Only A01 can call it. Pass the verified prompt through unchanged.
- OMP stays on normal `write` approvals, or `--omp-approval-mode always-ask`. Grok headless dispatch on that branch fails closed because the installed interface does not support the old stdin transport. The Cursor headless-runner ban in the section above still applies: this pending bootstrap is not a reason to start `scripts/swarm_run.py` from a Cursor session.
