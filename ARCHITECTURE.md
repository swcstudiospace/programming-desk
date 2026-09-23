# Architecture — Seven-Seat Programming Desk

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

The third is **unassigned work**. A desk channel that invents tasks will have specialists editing
code nobody asked for. LEAD, outside that channel, is the answer: Ove talks to LEAD, LEAD writes
tickets, specialists execute tickets. The loop is `docs/desk-operating-model.md`.

## 2. Seven seats, six in the channel

The live Programming Desk chat channel holds **at most six members**. LEAD is not one of them.
SYSTEMS, WEB, ANDROID, IOS, INFRA, and QUALITY fill those seats. LEAD orchestrates by ticket and
by direct message, from outside the channel.

```
                              Ove (human)
                                   │
                                   ▼
                    ┌──────────────────────────────────┐
                    │  LEAD — bot-00-programming-lead  │
                    │  outside the desk channel        │
                    │  tickets · dispatch · consolidate│
                    └────────────────┬─────────────────┘
                                     │ assigns tickets
     ┌──────────┬──────────┬─────────┴────────┬──────────┬──────────────┐
     │          │          │                  │          │              │
┌────▼─────┐┌───▼────┐┌────▼─────┐┌───────────▼┐┌────────▼─────┐┌───────▼──────┐
│ SYSTEMS  ││  WEB   ││ ANDROID  ││    IOS     ││    INFRA     ││   QUALITY    │
│  bot-01  ││ bot-02 ││  bot-03  ││   bot-04   ││    bot-05    ││    bot-06    │
│ rust, py ││ts,deno ││ kotlin   ││   swift    ││  tf, k8s, ci ││ reads all    │
└────┬─────┘└───┬────┘└────┬─────┘└─────┬──────┘└──────┬───────┘│ writes gates │
     │          │          │            │             │        └──────┬───────┘
     └──────────┴──────────┴────────────┴─────────────┘               │
                               │                                      │
                      ┌────────▼─────────┐                            │
                      │    contracts/    │◀───────────────────────────┘
                      │ the only shared  │
                      │     surface      │
                      └──────────────────┘

     Programming Desk channel: the six specialists. LEAD is not in it.
```

| Seat | Bot id | Owns | Primary languages |
|---|---|---|---|
| **LEAD** | `bot-00-programming-lead` | Desk operating model, its prompt, its receipts. Not specialist code. | — |
| **SYSTEMS** | `bot-01-systems-backend` | Services, APIs, data layer, performance-critical code | Rust, Python |
| **WEB** | `bot-02-web-edge` | Browser frontend, edge functions, Vercel deploys | TypeScript, Deno |
| **ANDROID** | `bot-03-android` | Android app, Compose UI, Gradle, Play release | Kotlin |
| **IOS** | `bot-04-ios` | iOS app, SwiftUI, Xcode, App Store release | Swift |
| **INFRA** | `bot-05-infrastructure` | IaC, Kubernetes, CI/CD, remote dev machine, observability | HCL, YAML, Bash |
| **QUALITY** | `bot-06-quality-security` | Review, test strategy, secrets, supply chain, the gates themselves | — |

QUALITY is deliberately asymmetric: **read access everywhere, write access almost nowhere**. It
owns `ci/gates/`, `contracts/`, `SECURITY.md` and `ownership.yaml`, and almost nothing else. A
reviewer that can rewrite the code it is reviewing is not a reviewer. `docs/desk-operating-model.md`
is LEAD's, not QUALITY's.

In-repo identity is the callsign and bot id. Live agent UUIDs live in the Grok Bot agent map.
They are not stored here and they are not required runtime configuration.

## 3. The ownership model

Every path resolves to exactly one owner via `ownership.yaml`. Last matching pattern wins.

**A bot may not modify a path it does not own.** `ci/gates/check_ownership.py` fails the build
otherwise, and it also fails on *unowned* paths — a file matching no pattern is precisely where
two bots collide silently, so it is treated as an error rather than a default.

This is what makes platform decomposition workable. Without it, "add push notifications" becomes
SYSTEMS, ANDROID, IOS and INFRA all editing the same branch, and the resulting merge is decided
by timing.

### Cross-bot features: LEAD orchestrates, contract first

A feature spanning seats is not one bot doing everything, and it is not a specialist nominating
itself. LEAD is the integrating orchestrator.

```
1. LEAD             one ticket per specialist; names paths and acceptance
2. CONTRACT PR      merged to contracts/ FIRST, with every consumer acknowledging
3. IMPLEMENTATION   each specialist, own paths, own receipt, in parallel
4. QUALITY          reviews the receipts and the change; does not patch the code
5. LEAD             consolidates for Ove
```

The contract merges before any implementation. Specialists then work in parallel against a fixed
interface instead of against each other's moving code. Full protocol in
`docs/cross-bot-protocol.md`. Day-to-day intake is `docs/desk-operating-model.md`.

Breaking a contract requires a version bump, a migration note, and an acknowledgement from every
consumer listed in `contract_consumers`. This is the control that stops a field rename in the API
silently breaking the iOS client. LEAD chases the acknowledgements. LEAD does not ack on a
specialist's behalf.

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

The seven-seat desk does not add a seventh gate and does not relax these six. LEAD's tickets do
not override them. Details and the evidence each produces: `docs/quality-gates.md`.

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

LEAD's consolidation receipt cites commands LEAD actually ran, and points at specialist receipt
paths. It does not restate their test runs as LEAD's own evidence.

The design point: the gate does not ask a bot whether it verified something. It asks for the exit
code. A model can be confident about a claim; it cannot fabricate a `0` that CI will re-run.

## 6. What each seat may not do

| Seat | Must not |
|---|---|
| All | Claim completion without a receipt; modify unowned paths; commit secrets; disable a gate; invent work from desk chat |
| LEAD | Implement specialist paths; join the six-member Programming Desk channel; treat chat as a ticket; approve LEAD's own operating-model edit |
| SYSTEMS | Change a contract without consumer acks; run a destructive migration without approval |
| WEB | Promote to Vercel production without a rollback plan; ship a secret to the client bundle |
| ANDROID | Upload to Play production without staged rollout; bump `minSdk` without consumer sign-off |
| IOS | Submit to App Store without a reviewed release note; change entitlements silently |
| INFRA | `terraform apply` to production without a reviewed plan; delete stateful resources without approval |
| QUALITY | Modify implementation code to make a test pass; approve its own work; dispatch other specialists |

That last row matters. The reviewer fixing the code it reviews is how a quality gate becomes a
rubber stamp.

## 7. Escalation

| Condition | Behaviour |
|---|---|
| Gate fails | Stop. Report the gate and the reason to LEAD. Never disable, never `--no-verify`. |
| Ownership conflict | Escalate to LEAD. Open a contract-first thread. Do not edit the other seat's paths. |
| Desk chat suggests work | Ask LEAD for a ticket. Do not start. |
| Direct ask from Ove | Do the work. Copy LEAD. |
| Cannot verify a claim | Move it to `unverified` and say so. Do not assert it. |
| Test fails and the fix is unclear | Investigate the code under test before the test. A failing test is usually correct. |
| Destructive op needed | Human approval, recorded in the receipt, before execution. A ticket is not that approval. |
| Contract change needed mid-implementation | Stop implementation. LEAD amends the tickets. Re-acknowledge. |

## 8. Stack

- **Languages:** Rust, Python, TypeScript/Deno, Kotlin, Swift
- **Edge/hosting:** Vercel
- **Infra:** Terraform, Kubernetes, GitHub Actions
- **Remote dev:** dedicated Linux dev machine — see `skills/platforms/remote-dev-machine/`
- **Models:** Opus for LEAD, SYSTEMS, and QUALITY (orchestration, design, and review judgement); Sonnet for WEB, ANDROID, IOS, and INFRA (throughput)
