# Programming Agent System

A six-bot operating system for software development across backend, web, Android, iOS and
infrastructure — decomposed by platform, with ownership and verification enforced in CI.

---

## Quick orientation

| If you want to | Read |
|---|---|
| Understand the six bots and why they are shaped this way | `ARCHITECTURE.md` |
| Know who owns which file | `ownership.yaml` |
| See the gates and what enforces each | `docs/quality-gates.md` |
| Build a feature spanning several bots | `docs/cross-bot-protocol.md` |
| Deploy the bots | `prompts/` |
| Understand a platform in depth | `skills/platforms/` |
| Run or extend the gates | `ci/gates/` |

---

## The six bots

```
                    ┌───────────────────────────────┐
                    │  Bot 6 — Quality & Security   │
                    │  reads all, writes almost none│
                    └───────────────┬───────────────┘
   ┌──────────┬──────────┬──────────┴─┬──────────┬──────────────┐
┌──▼───────┐┌─▼────────┐┌▼─────────┐┌─▼────────┐┌▼─────────────┐
│  Bot 1   ││  Bot 2   ││  Bot 3   ││  Bot 4   ││    Bot 5     │
│ Systems  ││  Web &   ││ Android  ││   iOS    ││Infrastructure│
│ Backend  ││   Edge   ││          ││          ││   & DevEx    │
│rust,py   ││ts,deno   ││ kotlin   ││  swift   ││  tf,k8s,ci   │
└──────────┘└──────────┘└──────────┘└──────────┘└──────────────┘
                    └──────▶ contracts/ ◀──────┘
                       the only shared surface
```

Bot 6 is deliberately asymmetric: read access everywhere, write access almost nowhere. A reviewer
that can rewrite the code it reviews is not a reviewer.

---

## The two structural decisions

### 1. Verification receipts

**The failure mode of a coding agent is not writing bad code. It is writing plausible code,
reasoning convincingly about why it works, and reporting success without executing it.**

Every completion claim is backed by a receipt recording commands actually run and their actual
exit codes:

```json
{
  "commands": [
    { "cmd": "pytest tests/api", "exit_code": 1 },
    { "cmd": "pytest tests/api", "exit_code": 0 }
  ],
  "claims": [
    { "claim": "reproduced the failure", "evidence_command_index": 0, "expects_failure": true },
    { "claim": "fix resolves it",        "evidence_command_index": 1 }
  ],
  "unverified": ["integration suite not run — no database in this environment"],
  "approved_by": "bot-06-quality-security"
}
```

The gate does not ask whether a bot verified something. It asks for the exit code, and CI can
re-run the command. A model can be confident about a claim it never tested; it cannot fabricate a
`0` that survives re-execution.

Three properties do the work: every claim cites a command, `unverified` is mandatory and specific,
and a bot cannot approve itself. `expects_failure` supports the reproduce-first pattern — and the
gate checks that such a command actually *did* fail, so the flag cannot launder a broken claim.

### 2. Path ownership

Platform decomposition buys deep platform expertise and costs a clear owner for anything crossing
platforms. `ownership.yaml` pays that cost: every path resolves to exactly one bot, and a path
matching nothing is a **build failure** — an unowned file is precisely where two bots collide
silently.

Cross-platform features use the contract-first protocol: the contract merges **before** any
implementation, every consumer acknowledges, then all bots implement in parallel against a fixed
interface instead of against each other's moving code.

---

## Quality gates

| Gate | Rule | Script |
|---|---|---|
| **G-1** | No bot modifies a path it does not own; no unowned paths | `check_ownership.py` |
| **G-2** | No completion claim without a verification receipt | `check_receipt.py` |
| **G-3** | No secret committed | `check_secrets.py` |
| **G-4** | Breaking contract change needs version + migration + consumer acks | `check_contracts.py` |
| **G-5** | No deploy without a tested rollback plan | `check_rollback.py` |
| **G-6** | Destructive operations need recorded human approval | `check_rollback.py` |

Gates are executable and fail the build. Not prompt text — prompt text is advisory and a non-zero
exit code is not.

```bash
python3 ci/gates/run_all.py --bot bot-01-systems-backend \
    --base origin/main --receipt .receipts/bot-01-systems-backend/fix-api.json
```

---

## Verification

Everything here has been run.

```bash
pip install pyyaml pytest

# XML prompts parse
python3 -c "import xml.etree.ElementTree as ET,glob; [ET.parse(f) for f in glob.glob('prompts/**/*.xml',recursive=True)]"

# Ownership manifest self-check
python3 ci/gates/check_ownership.py --validate-manifest

# Gate test suite — 86 tests against real fixtures
python3 -m pytest ci/tests/ -v
```

**Status:** 7/7 prompts parse · 86/86 gate tests pass · manifest validates · end-to-end verified
against a real git repository.

The gate suite found four real bugs during development, including one design flaw: the receipt
gate rejected any claim citing a failing command, which broke the reproduce-first pattern the
skill documentation recommends. End-to-end testing then found that `.receipts/` was an unowned
path every bot needed to write to. Both are fixed and covered by regression tests.

---

## Setup

### 1. Bot prompts

Each bot's system prompt is `prompts/_shared/core-directives.xml` **prepended to** its own file.
Substitute the `{{PLACEHOLDER}}` values.

Suggested models: Opus for Bots 1 and 6 (design and review judgement), Sonnet for 2–5 (throughput).

### 2. Ownership manifest

Adapt `ownership.yaml` to your repository layout. Then:

```bash
python3 ci/gates/check_ownership.py --validate-manifest
```

The manifest ships with a reference layout (`services/`, `web/`, `android/`, `ios/`, `infra/`).
Change the patterns, not the model — one owner per path is what makes this work.

### 3. CI and hooks

```bash
cp ci/.github/workflows/gates.yml .github/workflows/gates.yml
./ci/hooks/install.sh
```

Branch naming convention: `bot-03-android/feat-push-notifications`. The workflow derives the acting
bot from the prefix — G-1 cannot attribute a change without it.

Make the gates **required status checks**. A gate that can be merged past is a suggestion.

### 4. Remote development machine

`skills/platforms/remote-dev-machine/SKILL.md` covers the shared dev box.

> **One thing to address:** the machine is currently configured for root access
> (`root@187.77.130.10`). Shared development as root means no permission boundary between a
> mistyped path and the system, no attribution of who ran what, and root-owned build artefacts
> that break other users. §6 of that skill has the fix — a non-root working user with sudo, about
> an hour of work. Until then, every command on that box is a production command.
>
> I have not made that change: altering SSH access affects everyone using the machine and is
> itself a G-6 operation.

---

## Layout

```
├── ARCHITECTURE.md              Six bots, ownership model, gates, escalation
├── ownership.yaml               Path → owner. The manifest G-1 enforces
├── docs/
│   ├── quality-gates.md         G-1..G-6: rule → script → evidence
│   ├── cross-bot-protocol.md    Contract-first protocol for multi-bot features
│   └── handoff-contracts.md     Event envelope and payload schemas
├── prompts/
│   ├── _shared/core-directives.xml
│   └── bot-0{1..6}-*.xml
├── skills/                      L1 summary → L2 method → L3 references
│   ├── verification-receipts/   The G-2 artefact. Always loaded
│   ├── contract-first-changes/  Breaking-change analysis
│   ├── code-review/             Review order; what to let go
│   ├── debugging/               Reproduce → isolate → understand → fix → verify
│   ├── platforms/               rust, python, deno-typescript, android, ios,
│   │                            vercel, terraform-k8s, remote-dev-machine
│   └── security/                secrets-handling, supply-chain
└── ci/
    ├── gates/                   Six executable gate scripts + run_all.py
    ├── hooks/                   pre-commit (secret scan) + install.sh
    ├── tests/test_gates.py      86 tests against real fixtures
    └── .github/workflows/       CI workflow, including a gate self-test job
```

---

## What this system deliberately does not allow

- Claiming completion without a verification receipt
- Modifying a path owned by another bot
- Disabling, bypassing or weakening a gate — including `--no-verify`, `-x test`, `|| true`
- Committing a secret
- Destructive operations without recorded human approval
- A bot approving its own work
- A reviewer fixing the code it is reviewing

Each is enforced in a gate script, not only in prompt text.

---

## Growing the skills tree

Add a skill when a bot has made the same class of mistake **twice**. Skills written ahead of
evidence encode guesses.

Likely next: `performance-profiling`, `incident-response`, `database-design`, `api-versioning`,
`accessibility`, and per-service `domains/<service>` skills once services grow their own
conventions.
