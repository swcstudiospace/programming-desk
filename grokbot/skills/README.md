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

| Skill | Canonical file | Ref while pending |
|---|---|---|
| `ultrathink-protocol` | `swcstudiospace/claude-ultrathink` `hosts/grok-bot/ultrathink-protocol/SKILL.md` | `grokbot/ultrathink-skill-adapter`, [pull request 21](https://github.com/swcstudiospace/claude-ultrathink/pull/21) |
| `ultrathink-off` | `hosts/grok-bot/commands/ultrathink-off/SKILL.md` in the same repository | same draft |
| `ultrathink-on` | `hosts/grok-bot/commands/ultrathink-on/SKILL.md` | same draft |
| `ultrathink-quick` | `hosts/grok-bot/commands/ultrathink-quick/SKILL.md` | same draft |
| `ultrathink-skip` | `hosts/grok-bot/commands/ultrathink-skip/SKILL.md` | same draft |
| `ultrathink-status` | `hosts/grok-bot/commands/ultrathink-status/SKILL.md` | same draft |
| `ultrathink-track` | `hosts/grok-bot/commands/ultrathink-track/SKILL.md` | same draft |
| `swarm-cloud-dispatch` | `swcstudiospace/agent-swarm` `grokbot/skills/swarm-cloud-dispatch/SKILL.md` | `grokbot/cursor-agents-export`, [pull request 12](https://github.com/swcstudiospace/agent-swarm/pull/12) |
| `desk-shared-memory` | `grokbot/skills/desk-shared-memory/SKILL.md` in this repository | `bot-00-programming-lead/grokbot-skills-index`, [pull request 70](https://github.com/swcstudiospace/programming-desk/pull/70) |
| `desk-run` | `grokbot/skills/desk-run/SKILL.md` in this repository | `bot-00-programming-lead/grokbot-skills-index`, [pull request 70](https://github.com/swcstudiospace/programming-desk/pull/70) |

`desk-run` is the umbrella. It chains `ultrathink-protocol`, `desk-shared-memory` and `swarm-cloud-dispatch` into one `/desk-run` command. Its canonical file is in this repository. The other two stay in the repositories named above; this directory does not copy them.

## What is checked in here

- `index.json` — the list.
- `desk-shared-memory/SKILL.md` — the canonical memory skill. It names only the eight core gateway tools.
- `desk-run/SKILL.md` — the canonical `/desk-run` skill.
