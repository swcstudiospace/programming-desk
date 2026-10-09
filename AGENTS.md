# Programming Desk — instructions for Cursor cloud agents

This repository is the seven-seat Programming Desk
(`swcstudiospace/programming-desk`). Programming Lead orchestrates. SYSTEMS, WEB,
ANDROID, IOS and INFRA implement in the paths they own. QUALITY
(`bot-06-quality-security`) reviews and owns the gates. Orientation:
[README.md](README.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

## Where the rules live

The linked file is the rule. Do not treat a summary as a substitute.

| Topic | File |
|---|---|
| Gates G-1…G-6, and why Greptile is not one of them | [docs/quality-gates.md](docs/quality-gates.md) |
| Features that cross seats | [docs/cross-bot-protocol.md](docs/cross-bot-protocol.md) |
| GitHub as source of truth, draft PR, Greptile | [docs/github-sot-orchestration.md](docs/github-sot-orchestration.md) |
| Seven-seat operating model | [docs/desk-operating-model.md](docs/desk-operating-model.md) |
| Greptile merge gate (QUALITY records the verdict) | [skills/greptile-merge-gate/SKILL.md](skills/greptile-merge-gate/SKILL.md) |
| Receipt shape (G-2) | [skills/verification-receipts/SKILL.md](skills/verification-receipts/SKILL.md) |
| Prime directives shared by every seat | [prompts/_shared/core-directives.xml](prompts/_shared/core-directives.xml) |
| Path → owner | [ownership.yaml](ownership.yaml) |

## Path ownership, before the first edit

Every path resolves to exactly one seat in [ownership.yaml](ownership.yaml).
Last match wins. A path that matches nothing is unowned, and
`python3 ci/gates/check_ownership.py` fails the build. Resolve the paths you
will edit against that manifest before changing them. Cross-seat work follows
[docs/cross-bot-protocol.md](docs/cross-bot-protocol.md).

`AGENTS.md` and `.cursor/**` (including `.cursor/agents/**` and
`.cursor/rules/**`) are owned by `bot-06-quality-security`.

## Branch and pull request

Work on a feature branch and open a **draft** pull request into the default
branch. Do not merge, enable auto-merge, force-push, or delete branches.

[`.github/workflows/gates.yml`](.github/workflows/gates.yml) derives the acting
bot from the branch prefix `bot-0N-name/...`.
[docs/github-sot-orchestration.md](docs/github-sot-orchestration.md) §3.1 states
the same convention. A branch that does not match fails G-1 attribution in that
workflow.

## Receipts

No completion claim without a receipt under `.receipts/<seat>/<task-id>.json`.
The format is
[skills/verification-receipts/SKILL.md](skills/verification-receipts/SKILL.md).
Record commands you actually ran and their exit codes. `unverified` is
mandatory and must be specific. `approved_by` is never the authoring bot. When
QUALITY authors the change, the stamp comes from LEAD
(`bot-00-programming-lead`) or a human, and it stays absent until that review
([docs/quality-gates.md](docs/quality-gates.md)).

`.gitignore` ignores `.receipts/**/*.json`. Track a new receipt with
`git add -f`.

## Greptile

After the draft PR exists, the Greptile merge gate is run by QUALITY via
Programming Lead
([skills/greptile-merge-gate/SKILL.md](skills/greptile-merge-gate/SKILL.md)).
Do not claim the change is merge-ready while any Greptile finding is
unaddressed. A review that is `FAILED`, `SKIPPED`, or unavailable is a blocker
to report, not a pass. Greptile does not replace G-1…G-6.

## Secrets

Do not print, commit, or echo tokens, keys, passphrases, bus secrets, tailnet
names, or `*.railway.internal` hosts. Reference environment variables by name
only. G-3 is `python3 ci/gates/check_secrets.py`.

## Run the gates locally

Install matches the gate workflow (`pip install pyyaml` on the gates job,
`pip install pyyaml pytest` on the gate-self-test job):

```bash
pip install pyyaml pytest
python3 ci/gates/check_ownership.py --validate-manifest
python3 ci/gates/check_ownership.py --bot <bot-id> --base origin/main
python3 ci/gates/check_desk_integrity.py --repo .
python3 ci/gates/check_secrets.py --base origin/main
python3 ci/gates/check_contracts.py --base origin/main
# For contract-surface edits, point check_contracts.py at the change record:
# python3 ci/gates/check_contracts.py --base origin/main --change contracts/changes/<change-id>.yaml
python3 ci/gates/check_rollback.py --receipt .receipts/<bot-id>/<task-id>.json
python3 ci/gates/check_receipt.py --receipt .receipts/<bot-id>/<task-id>.json --bot <bot-id> --strict
python3 -m pytest ci/tests/ -v
```

The bare `check_contracts.py --base origin/main` is only for a diff that
touches no contract surface. The gate does not search for a change document.
When the diff touches one, this is the exact invocation
([docs/quality-gates.md](docs/quality-gates.md)):

```bash
python3 ci/gates/check_contracts.py --base origin/main --change contracts/changes/<change-id>.yaml
```

`check_receipt.py --strict` matches the G-2 step in
[`.github/workflows/gates.yml`](.github/workflows/gates.yml). G-2 is expected
to fail on a missing `approved_by` until an independent reviewer stamps the
receipt. Any other G-2 failure is yours to fix before pushing.

## Running the swarm here

`.cursor/agents/` is the Cursor export of agent-swarm (`a01-orchestrator`
through `a15-docs`), copied by `scripts/_install_cursor.py` from
[swcstudiospace/agent-swarm](https://github.com/swcstudiospace/agent-swarm)
commit `663969821a4b9c844de1d529c85670abc863202f` (`main`). This repo does not vendor that runtime.
[`.cursor/environment.json`](.cursor/environment.json) keeps the gate install
and clones that commit to `$HOME/.local/share/agent-swarm`, then exports
`SWARM_ROOT` to that absolute path. The same path is written for later login
shells (`/etc/profile.d/swarm-root.sh`) and interactive bash (`~/.bashrc`).

Brief a run by spawning `a01-orchestrator` (`subagent_type`
`a01-orchestrator`) with the brief. A01 may spawn `a02-requirements` through
`a15-docs`. Those specialists must not spawn further subagents. Swarm tools
are `python3 "$SWARM_ROOT/scripts/<tool>.py" --root <git toplevel> --json`.
If `SWARM_ROOT` is unset, stop and report `BLOCKED` with `needs` `SWARM_ROOT`.
Do not treat this repo's `scripts/` as swarm tools.

The session is advisory. `SWARM_ED25519_KEY` and `SWARM_REQUIRE_KEY` are
unset, so a gate script records nothing and nothing here counts as APPROVED.
A missing signing key is the expected keyless state and is not an E-DEP
failure. The merge gate is Greptile via Desk Quality. Substrate wiring is
off. Do not start an unattended headless runner. The rule file is
[`.cursor/rules/agent-swarm.mdc`](.cursor/rules/agent-swarm.mdc).
