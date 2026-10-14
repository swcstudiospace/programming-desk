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
| `pending_pr` | The open draft pull request, when one exists. Omit the key when there is no open draft. |
| `owner_seat` | The desk seat that re-saves the skill: `bot-00-programming-lead`. `claude-ultrathink` and `agent-swarm` have no `ownership.yaml`, so this is the desk seat, not a path owner in those repositories. |
| `purpose` | One line, taken from the skill. |

## One-way flow

The standing source is the repository default branch, after the indexed change has merged. Lead re-saves that `SKILL.md` into Grok Bot. Grok Bot's copy never writes back.

Re-save is manual. Grok Bot keeps skills in one account-wide private library, and this repository has no installer for that library. Until a Marketplace plugin exists, paste the file and save it as a skill named the frontmatter `name` (desktop only). That is the route in `docs/upgrade-plan-desk-v2.md` §8.3. A reviewed pull request here does not by itself change what a Bot has loaded.

A copy already saved in Grok Bot is a mirror. A fix is a pull request against the indexed repository, then another re-save after that pull request merges. The same one-way rule as `skills/pack-sync`: unmerged work is not the standing source, and nothing flows from the Bot back to git.

While `pending` is true, the file exists on `ref` and not on `default_branch`. Re-save from `ref` only to try the draft. After the pull request merges, re-save again from `default_branch` and treat that as the source.

When `pending` is false and `pending_pr` is set, the path is already on `default_branch` and that draft changes the file. Re-save from `default_branch` for the standing copy. Re-save from the draft branch only to try the unmerged text. After that pull request merges, clear `pending_pr` and re-save from `default_branch`.

## Skills

| Skill | Canonical file | Ref |
|---|---|---|
| `ultrathink-protocol` | `swcstudiospace/claude-ultrathink` `hosts/grok-bot/ultrathink-protocol/SKILL.md` | `main` |
| `ultrathink-plan` | `hosts/grok-bot/skills/ultrathink-plan/SKILL.md` in the same repository | `main` |
| `ultrathink-kickoff` | `hosts/grok-bot/skills/ultrathink-kickoff/SKILL.md` | `main` |
| `ultrathink-sync` | `hosts/grok-bot/skills/ultrathink-sync/SKILL.md` | `main` |
| `ultrathink-ship` | `hosts/grok-bot/skills/ultrathink-ship/SKILL.md` | `main` |
| `ultrathink-off` | `hosts/grok-bot/commands/ultrathink-off/SKILL.md` | `main` |
| `ultrathink-on` | `hosts/grok-bot/commands/ultrathink-on/SKILL.md` | `main` |
| `ultrathink-quick` | `hosts/grok-bot/commands/ultrathink-quick/SKILL.md` | `main` |
| `ultrathink-skip` | `hosts/grok-bot/commands/ultrathink-skip/SKILL.md` | `main` |
| `ultrathink-status` | `hosts/grok-bot/commands/ultrathink-status/SKILL.md` | `main` |
| `ultrathink-track` | `hosts/grok-bot/commands/ultrathink-track/SKILL.md` | `main` |
| `swarm-cloud-dispatch` | `swcstudiospace/agent-swarm` `grokbot/skills/swarm-cloud-dispatch/SKILL.md` | `main` |
| `desk-shared-memory` | `grokbot/skills/desk-shared-memory/SKILL.md` in this repository | `main` |
| `desk-run` | `grokbot/skills/desk-run/SKILL.md` in this repository | `main`, open draft [pull request 224](https://github.com/swcstudiospace/programming-desk/pull/224) |

`desk-run` is the umbrella for `/desk-run` and `/ultrathink`. It orders `ultrathink-protocol` through `ultrathink-plan`, `ultrathink-kickoff`, `ultrathink-sync` and `ultrathink-ship`, then `desk-shared-memory` and `swarm-cloud-dispatch`. When a prompt invokes a `/gsd-*` command it also runs the mapped pstack skills beside that command, the same mapping as claude-ultrathink pull request 27 (`docs/how-to/use-pstack-with-cursor.md` on `main`). Its canonical file is in this repository. The other skills stay in the repositories named above; this directory does not copy them.

Pull requests 21 (claude-ultrathink), 12 (agent-swarm) and 70 (this repository) have merged. Those rows are `pending: false` and `ref: main`. The draft branch `grokbot/cursor-agents-export` is gone, so it is not a re-save ref.

## What is checked in here

- `index.json` — the list.
- `desk-shared-memory/SKILL.md` — the canonical memory skill. It names only the eight core gateway tools.
- `desk-run/SKILL.md` — the canonical `/desk-run` skill.
