# Programming Agent System

A **seven-seat** operating system for software development across backend, web, Android, iOS and
infrastructure — decomposed by platform, with ownership and verification enforced in CI.
**Programming Lead** orchestrates from outside the desk channel; six specialists execute.

---

## Quick orientation

| If you want to | Read |
|---|---|
| Understand the seven seats and the orchestrator pattern | `ARCHITECTURE.md` |
| How LEAD tickets and reports | `docs/desk-operating-model.md` |
| Know who owns which file | `ownership.yaml` |
| See the gates and what enforces each | `docs/quality-gates.md` |
| Build a feature spanning several bots | `docs/cross-bot-protocol.md` |
| Deploy the bots | `prompts/` |
| Understand a platform in depth | `skills/platforms/` |
| Run or extend the gates | `ci/gates/` |

---

## The seven seats

```
         Ove ──▶ LEAD (outside channel) ──tickets──▶ specialists
                      │
         ┌────────────┴──────────────────────────────────────┐
         │ Desk channel (max 6): SYSTEMS WEB ANDROID IOS     │
         │                     INFRA QUALITY                 │
         └───────────────────────────────────────────────────┘
                              QUALITY reviews (asymmetric)
```

| Seat | Role |
|---|---|
| **LEAD** | Intake, tickets, dispatch, consolidate, report to Ove |
| **SYSTEMS / WEB / ANDROID / IOS / INFRA** | Implement in owned paths; report receipts to LEAD |
| **QUALITY** | Review, gates, contracts — read everywhere, write almost nowhere |

Lead stays outside because the Programming Desk channel allows at most six members. Details:
`docs/desk-operating-model.md`.

---

## The two structural decisions

### 1. Verification receipts

**The failure mode of a coding agent is not writing bad code. It is writing plausible code,
reasoning convincingly about why it works, and reporting success without executing it.**

Every completion claim is backed by a receipt recording commands actually run and their actual
exit codes. LEAD consolidates specialist receipts and QUALITY approval before telling Ove
something is done — LEAD does not fabricate evidence.

### 2. Path ownership

Platform decomposition buys deep platform expertise and costs a clear owner for anything crossing
platforms. `ownership.yaml` pays that cost: every path resolves to exactly one bot, and a path
matching nothing is a **build failure**. Cross-platform features use the contract-first protocol
with LEAD as integrating orchestrator.

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

# XML source prompts parse (core + seven seat files).
# prompts/{LEAD,SYSTEMS,WEB,ANDROID,IOS,INFRA,QUALITY}.xml and prompts-assembled/
# are those sources concatenated for runtime load, so they are two XML roots.
python3 -c "import xml.etree.ElementTree as ET,glob; files=sorted(glob.glob('prompts/bot-*.xml')+glob.glob('prompts/_shared/*.xml')); assert len(files)==8, files; [ET.parse(f) for f in files]"

# Ownership manifest self-check
python3 ci/gates/check_ownership.py --validate-manifest

# Gate test suite — 86 tests against real fixtures
python3 -m pytest ci/tests/ -v
```

**Status:** 8/8 prompts parse (core + 7 seats) · 86/86 gate tests pass · manifest validates · end-to-end verified
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

Suggested models: Opus for LEAD, SYSTEMS, and QUALITY (judgement); Sonnet for WEB/ANDROID/IOS/INFRA (throughput).

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

