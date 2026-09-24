# Architecture — Seven-Seat Programming Operating System

## 1. Design premise

The recruitment system's central problem was **lawfulness**: a bot could do something that looked
productive and was illegal. This system's central problem is different.

**The failure mode here is a bot claiming work is done when it has not verified that it is.**

Hallucinated success is the defining failure of coding agents. A bot writes a function, reasons
convincingly about why it works, reports completion, and has never executed it. Every other
quality problem downstream — broken builds, failed releases, regressions found in production —
traces back to a completion claim that was never grounded in an observation.

So the artefact this system is built around is the **verification receipt**: a machine-checkable
record of commands actually run and their actual exit codes. A bot that cannot produce a receipt
has not finished, regardless of how confident its summary reads. `ci/gates/check_receipt.py`
enforces this, and no bot can approve its own.

The second structural problem is a consequence of decomposing by platform rather than by
lifecycle: **ownership collision**. One feature spanning API, web and mobile means three bots on
the same branch with no clear authority. Section 3 is the answer.

The third structural problem is **operator interface**: when Ove messages the desk channel,
work dissolves into chat vibes. Section 2a is the answer — Programming Lead sits **in** the
channel with the five build seats and still assigns by concrete 1:1 tickets. QUALITY is the
off-channel seat (platform max 6).

## 2. The seven seats

```
                    Ove (operator)
                         │
                         ▼
              ┌──────────────────────┐
              │  LEAD — Programming  │  IN the channel
              │  Lead / Orchestrator │  tickets via SendToAgent
              │  bot-00              │  reports to Ove 1:1
              └──────────┬───────────┘
                         │ dispatch / consolidate
         ┌───────────────┼───────────────────────────────┐
         │               │                               │
         ▼               ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│              Programming Desk channel (max 6)               │
│  LEAD │ SYSTEMS │ WEB │ ANDROID │ IOS │ INFRA               │
└─────────────────────────────────────────────────────────────┘

                         ┌───────────────────────────────┐
                         │  QUALITY — Bot 6 off-channel  │
                         │  reads everything, owns gates │
                         └───────────────┬───────────────┘
                                         │ reviews
     ┌──────────────┬──────────────┬─────┴────────┬──────────────┐
     │              │              │              │              │
┌────▼─────┐  ┌─────▼────┐  ┌──────▼───┐  ┌───────▼──┐  ┌────────▼──────┐
│ SYSTEMS  │  │   WEB    │  │ ANDROID  │  │   IOS    │  │    INFRA      │
│ Backend  │  │  Edge    │  │          │  │          │  │Infrastructure │
│rust,py   │  │ts,deno   │  │ kotlin   │  │  swift   │  │   & DevEx     │
└────┬─────┘  └─────┬────┘  └──────┬───┘  └───────┬──┘  └────────┬──────┘
     │              │              │              │              │
     └──────────────┴──────────────┴──────────────┴──────────────┘
                                   │
                          ┌────────▼─────────┐
                          │    contracts/    │
                          │ the only shared  │
                          │     surface      │
                          └──────────────────┘
```

| Seat | Bot id | Owns | Primary languages |
|---|---|---|---|
| **LEAD** | bot-00-programming-lead | Orchestration docs + lead prompt + own receipts | — |
| **SYSTEMS** | bot-01-systems-backend | Services, APIs, data, design artifacts (`design/**`, `docs/design/**`) | Rust, Python |
| **WEB** | bot-02-web-edge | Browser, edge, Vercel, desktop shells (`desktop/**`, `electron/**`, `tauri/**`) | TypeScript, Deno |
| **ANDROID** | bot-03-android | Android app, Compose, Gradle, Play release under `android/**` | Kotlin |
| **IOS** | bot-04-ios | iOS app, SwiftUI, Xcode, App Store release under `ios/**` | Swift |
| **INFRA** | bot-05-infrastructure | IaC, Kubernetes, CI/CD, WEB3 ops (`web3/**`, `chains/**`). Not `**/*.proto`. | HCL, YAML, Bash |
| **QUALITY** | bot-06-quality-security | Review, secrets, supply chain, the gates, `**/*.proto` contract surface. Off-channel. | — |

QUALITY remains deliberately asymmetric: **read access everywhere, write access almost nowhere**.
It owns `ci/gates/`, `contracts/`, `SECURITY.md` and `ownership.yaml` (except the narrow Lead
overrides for `docs/desk-operating-model.md` and `prompts/bot-00-programming-lead.xml`). A
reviewer that can rewrite the code it is reviewing is not a reviewer.

### 2a. Orchestrator pattern (Lead in the channel, QUALITY off-channel)

Platform channels allow at most **six** members. The six are LEAD plus the five build seats.
QUALITY stays **off-channel** and receives post-build review tickets 1:1. LEAD still messages
seats 1:1 via `SendToAgent`. The Desk carries full human-visible traffic from build seats
(not status-only) and LEAD's required dispatch note. It is not the assignment bus. LEAD reports
to Ove in the LEAD↔Ove 1:1 and polls held (priority false) handoffs at the start of every turn.
Operating model: `docs/desk-operating-model.md`.

Real builds go through a **double uplift** before dispatch: a long nested XML spec, a Graph of
Thought of **5–8 nodes**, a Chain of Thought of **4–8 steps per node** (sequential by default),
dense Notion + Linear rows (one issue per node, one sub-issue per step), then a second uplift
that injects live tracker URLs. LEAD orchestrates that path (`skills/gotxcot-uplift`,
`skills/trackplan-dispatch`). LEAD does not implement product code. Default runtime is a Cursor
Cloud Agent; Hermes is optional and not a second source of truth. Policy:
`docs/gotxcot-cloud-pipeline.md`. GitHub remains the contract of record:
`docs/github-sot-orchestration.md`.

## 3. The ownership model

Every path resolves to exactly one owner via `ownership.yaml`. Last matching pattern wins.

**A bot may not modify a path it does not own.** `ci/gates/check_ownership.py` fails the build
otherwise, and it also fails on *unowned* paths — a file matching no pattern is precisely where
two bots collide silently, so it is treated as an error rather than a default.

LEAD does not own product code. Cross-bot features are opened by LEAD and executed by owning
seats against a fixed contract.

### Cross-bot features: contract-first

A feature spanning bots is not one bot doing everything. It is:

```
1. LEAD               intakes from Ove, nominates seats, opens tickets
2. CONTRACT PR        merged to contracts/ FIRST (QUALITY holds surface), consumers ack
3. IMPLEMENTATION     each specialist implements its side, in its own paths, in parallel
4. INTEGRATION        LEAD consolidates receipts; QUALITY reviews; LEAD reports to Ove
```

The contract merges before any implementation. Bots then work in parallel against a fixed
interface instead of against each other's moving code. Full protocol in
`docs/cross-bot-protocol.md`.

Breaking a contract requires a version bump, a migration note, and an acknowledgement from every
consumer listed in `contract_consumers`. This is the control that stops a field rename in the API
silently breaking the iOS client.

## 4. Quality gates

Enforced as executable scripts in CI and in a pre-commit hook. Not prompt text — prompt text is
advisory and a failing exit code is not.

| Gate | Rule | Enforced by |
|---|---|---|
| **G-1** | No bot modifies a path it does not own; no unowned paths | `check_ownership.py` |
| **G-2** | No completion claim without a verification receipt of commands actually run | `check_receipt.py` |
| **G-3** | No secret committed | `check_secrets.py` |
| **G-4** | Breaking contract change requires version bump + migration + consumer acks | `check_contracts.py` |
| **G-5** | No deploy without a tested rollback plan | `check_rollback.py` |
| **G-6** | Destructive operations require explicit human approval | `check_rollback.py` |

Details and the evidence each produces: `docs/quality-gates.md`.

## 5. Verification receipts

The core artefact. A receipt records what was actually run:

```json
{
  "task_id": "feat-push-notifications",
  "bot": "bot-03-android",
  "commands": [
    { "cmd": "./gradlew :app:testDebugUnitTest", "exit_code": 0, "duration_s": 47.2 },
    { "cmd": "./gradlew :app:lintDebug", "exit_code": 0, "duration_s": 12.8 }
  ],
  "claims": [
    { "claim": "unit tests pass", "evidence_command_index": 0 }
  ],
  "unverified": [
    "Behaviour on Android 8 — no device available in this environment"
  ]
}
```

Three properties make this work:

- **Every claim cites a command index.** A claim with no command behind it fails the gate.
- **`unverified` is mandatory and may not be empty-by-omission.** A bot that ran unit tests but
  no integration tests says so. Honest incompleteness is a passing state; silent incompleteness
  is not.
- **Receipts are append-only and a bot cannot sign its own approval.** QUALITY or a human does.
  LEAD consolidates; LEAD does not fabricate specialist evidence.

The design point: the gate does not ask a bot whether it verified something. It asks for the exit
code. A model can be confident about a claim; it cannot fabricate a `0` that CI will re-run.

## 6. What each seat may not do

| Seat | Must not |
|---|---|
| All | Claim completion without a receipt; modify unowned paths; commit secrets; disable a gate |
| LEAD | Implement specialist product code; fan out vague asks; invent done-ness without receipts |
| SYSTEMS | Change a contract without consumer acks; run a destructive migration without approval |
| WEB | Promote to Vercel production without a rollback plan; ship a secret to the client bundle |
| ANDROID | Upload to Play production without staged rollout; bump `minSdk` without consumer sign-off |
| IOS | Submit to App Store without a reviewed release note; change entitlements silently |
| INFRA | `terraform apply` to production without a reviewed plan; delete stateful resources without approval |
| QUALITY | Rewrite product code under review; approve its own gate changes without a human |

## 7. Skills and prompts

Each seat's full system prompt is `prompts/_shared/core-directives.xml` prepended to its
`prompts/bot-XX-*.xml` source. Assembled copies live in `prompts-assembled/` and
`prompts/{LEAD,SYSTEMS,...}.xml`. Runtime agents load `SYSTEM_PROMPT.xml` under
`/home/box/agent-data/agents/<uuid>/`.

Skills under `skills/` are progressive — load the platform SKILL.md decision tree, then only the
references required for the task.
