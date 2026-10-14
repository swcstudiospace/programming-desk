# grokbot/skills

Canonical sources for the skills Lead saves into Grok Bot. Owner: LEAD
(`ownership.yaml`, `grokbot/**`).

`index.json` is the list. One row per skill:

| Field | Meaning |
|---|---|
| `name` | Frontmatter `name`. Grok Bot invokes it as `/<name>`. |
| `repo` | `owner/name` of the git repository that holds the file. |
| `path` | Path of that `SKILL.md` inside `repo`. |
| `ref` | Git ref where `path` was verified to exist. |
| `default_branch` | The repository's default branch. After a pending row merges, this is the ref Lead re-saves from. |
| `pending` | True while `path` is not on `default_branch`. `ref` is then the open draft branch. |
| `pending_pr` | The open draft pull request, when one exists. |
| `owner_seat` | The desk seat that re-saves the skill: `bot-00-programming-lead`. `claude-ultrathink` and `agent-swarm` have no `ownership.yaml`, so this is the desk seat, not a path owner in those repositories. |
| `purpose` | One line, taken from the skill. |

## One-way flow

The standing source is the repository default branch, after the indexed change has merged. Lead re-saves that `SKILL.md` into Grok Bot. Grok Bot's copy never writes back.

Re-save is manual. Grok Bot keeps skills in one account-wide private library, and this repository has no installer for that library. Until a Marketplace plugin exists, paste the file and save it as a skill named the frontmatter `name` (desktop only). That is the route in `docs/upgrade-plan-desk-v2.md` §8.3. A reviewed pull request here does not by itself change what a Bot has loaded.

A copy already saved in Grok Bot is a mirror. A fix is a pull request against the indexed repository, then another re-save after that pull request merges. The same one-way rule as `skills/pack-sync`: unmerged work is not the standing source, and nothing flows from the Bot back to git.

While `pending` is true, the file exists on `ref` and not on `default_branch`. Re-save from `ref` only to try the draft. After the pull request merges, re-save again from `default_branch` and treat that as the source.

## Skills

| Skill | Canonical file | Ref |
|---|---|---|
| `ultrathink-protocol` | `swcstudiospace/claude-ultrathink` `hosts/grok-bot/skills/ultrathink-protocol/SKILL.md` | `c8c6290` on `main`. Desk mirror: `grokbot/skills/ultrathink-protocol/SKILL.md` |
| `ultrathink-on` | `hosts/grok-bot/skills/ultrathink-on/SKILL.md` | same pin. Desk mirror beside it |
| `ultrathink-think` | `hosts/grok-bot/skills/ultrathink-think/SKILL.md` | same pin. Desk mirror beside it |
| `ultrathink-engine` | `hosts/grok-bot/skills/ultrathink-engine/SKILL.md` | same pin. Desk mirror beside it |
| `ultrathink-last` | `hosts/grok-bot/skills/ultrathink-last/SKILL.md` | same pin. Desk mirror beside it |
| `ultrathink-track` | `hosts/grok-bot/skills/ultrathink-track/SKILL.md` | same pin. Desk mirror beside it |
| `ultrathink-lessons` | `hosts/grok-bot/skills/ultrathink-lessons/SKILL.md` | same pin. Desk mirror beside it |
| `ultrathink-hitl` | `hosts/grok-bot/skills/ultrathink-hitl/SKILL.md` | same pin. Desk mirror beside it |
| `ultrathink-teach-admin` | `hosts/grok-bot/skills/ultrathink-teach-admin/SKILL.md` | same pin. Desk mirror beside it |
| `ultrathink-off` | `hosts/grok-bot/skills/ultrathink-off/SKILL.md` | `c8c6290` on `main`. Not mirrored here |
| `ultrathink-quick` | `hosts/grok-bot/skills/ultrathink-quick/SKILL.md` | same pin. Not mirrored here |
| `ultrathink-skip` | `hosts/grok-bot/skills/ultrathink-skip/SKILL.md` | same pin. Not mirrored here |
| `ultrathink-status` | `hosts/grok-bot/skills/ultrathink-status/SKILL.md` | same pin. Not mirrored here |
| `ultrathink-pstack` | `grokbot/skills/ultrathink-pstack/SKILL.md` in this repository | this branch until it merges. Upstream has no file; plan and ship cite §1, §2 and §5 |
| `gsd-ship-pr` | `grokbot/skills/gsd-ship-pr/SKILL.md` in this repository | this branch until it merges |
| `gsd-runtime` | `grokbot/skills/gsd-runtime/SKILL.md` in this repository | this branch until it merges. Paragraphs marked `requires claude-ultrathink#34` need [pull request 34](https://github.com/swcstudiospace/claude-ultrathink/pull/34) at `87411ed` |
| `swarm-cloud-dispatch` | `swcstudiospace/agent-swarm` `grokbot/skills/swarm-cloud-dispatch/SKILL.md` | `grokbot/cursor-agents-export`, [pull request 12](https://github.com/swcstudiospace/agent-swarm/pull/12) |
| `desk-shared-memory` | `grokbot/skills/desk-shared-memory/SKILL.md` in this repository | `bot-00-programming-lead/grokbot-skills-index`, [pull request 70](https://github.com/swcstudiospace/programming-desk/pull/70) |
| `desk-run` | `grokbot/skills/desk-run/SKILL.md` in this repository | `bot-00-programming-lead/grokbot-skills-index`, [pull request 70](https://github.com/swcstudiospace/programming-desk/pull/70) |

`c8c6290` is claude-ultrathink `main` after #22–#30 and #32. Pull request #21 has merged. The native host files under `hosts/grok-bot/skills/` are what the bot runs. The skill-protocol adapter files (`hosts/grok-bot/ultrathink-protocol/SKILL.md` and `hosts/grok-bot/commands/<name>/SKILL.md`) stay beside that host and do not replace it.

`desk-run` is the umbrella. It chains `ultrathink-protocol`, `desk-shared-memory` and `swarm-cloud-dispatch` into one `/desk-run` command. Its canonical file is in this repository. `desk-shared-memory` is too. `swarm-cloud-dispatch` stays in agent-swarm.

The mirrored `ultrathink-*` files in this directory match the native host procedure at `c8c6290`, plus a pointer to `gsd-runtime` where the Omp flight matters. `gsd-ship-pr` records the plugin ship path and states that on Ming's VPS `ship.autoMerge` and `ship.deleteBranch` stay on. `gsd-runtime` records the Omp flight. Text that is true only on `fix/omp-planning-cancellation` @ `87411ed` is marked `requires claude-ultrathink#34`.

## What is checked in here

- `index.json` — the list.
- `desk-shared-memory/SKILL.md` — the canonical memory skill. It names only the eight core gateway tools.
- `desk-run/SKILL.md` — the canonical `/desk-run` skill.
