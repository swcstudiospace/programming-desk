# Architecture — Six-Bot Programming Operating System

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

## 2. The six bots

```
                         ┌───────────────────────────────┐
                         │  Bot 6 — Quality & Security   │
                         │  reads everything, owns gates │
                         └───────────────┬───────────────┘
                                         │ reviews
     ┌──────────────┬──────────────┬─────┴────────┬──────────────┬──────────────┐
     │              │              │              │              │              │
┌────▼─────┐  ┌─────▼────┐  ┌──────▼───┐  ┌───────▼──┐  ┌────────▼──────┐       │
│  Bot 1   │  │  Bot 2   │  │  Bot 3   │  │  Bot 4   │  │    Bot 5      │       │
│ Systems  │  │ Web &    │  │ Android  │  │   iOS    │  │Infrastructure │       │
│ Backend  │  │  Edge    │  │          │  │          │  │   & DevEx     │       │
│rust,py   │  │ts,deno   │  │ kotlin   │  │  swift   │  │ tf,k8s,ci     │       │
└────┬─────┘  └─────┬────┘  └──────┬───┘  └───────┬──┘  └────────┬──────┘       │
     │              │              │              │              │              │
     └──────────────┴──────────────┴──────────────┴──────────────┘              │
                                   │                                            │
                          ┌────────▼─────────┐                                  │
                          │    contracts/    │◀─────────────────────────────────┘
                          │ the only shared  │
                          │     surface      │
                          └──────────────────┘
```

| Bot | Owns | Primary languages |
|---|---|---|
| **1 — Systems & Backend** | Services, APIs, data layer, performance-critical code | Rust, Python |
| **2 — Web & Edge** | Browser frontend, edge functions, Vercel deploys | TypeScript, Deno |
| **3 — Android** | Android app, Compose UI, Gradle, Play release | Kotlin |
| **4 — iOS** | iOS app, SwiftUI, Xcode, App Store release | Swift |
| **5 — Infrastructure & DevEx** | IaC, Kubernetes, CI/CD, remote dev machine, observability | HCL, YAML, Bash |
| **6 — Quality & Security** | Review, test strategy, secrets, supply chain, the gates themselves | — |

Bot 6 is deliberately asymmetric: **read access everywhere, write access almost nowhere**. It
owns `ci/gates/`, `contracts/`, `SECURITY.md` and `ownership.yaml`, and nothing else. A reviewer
that can rewrite the code it is reviewing is not a reviewer.

## 3. The ownership model

Every path resolves to exactly one owner via `ownership.yaml`. Last matching pattern wins.

**A bot may not modify a path it does not own.** `ci/gates/check_ownership.py` fails the build
otherwise, and it also fails on *unowned* paths — a file matching no pattern is precisely where
two bots collide silently, so it is treated as an error rather than a default.

This is what makes platform decomposition workable. Without it, "add push notifications" becomes
Bot 1, 3, 4 and 5 all editing the same branch, and the resulting merge is decided by timing.

### Cross-bot features: contract-first

A feature spanning bots is not one bot doing everything. It is:

```
1. INTEGRATING BOT   owns the user-facing surface, drafts the contract change
2. CONTRACT PR       merged to contracts/ FIRST, with every consumer acknowledging
3. IMPLEMENTATION    each bot implements its side, in its own paths, in parallel
4. INTEGRATION       verified against the contract, not against another bot's code
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
- **Receipts are append-only and a bot cannot sign its own approval.** Bot 6 or a human does.

The design point: the gate does not ask a bot whether it verified something. It asks for the exit
code. A model can be confident about a claim; it cannot fabricate a `0` that CI will re-run.

## 6. What each bot may not do

| Bot | Must not |
|---|---|
| All | Claim completion without a receipt; modify unowned paths; commit secrets; disable a gate |
| 1 Backend | Change a contract without consumer acks; run a destructive migration without approval |
| 2 Web & Edge | Promote to Vercel production without a rollback plan; ship a secret to the client bundle |
| 3 Android | Upload to Play production without staged rollout; bump `minSdk` without consumer sign-off |
| 4 iOS | Submit to App Store without a reviewed release note; change entitlements silently |
| 5 Infrastructure | `terraform apply` to production without a reviewed plan; delete stateful resources without approval |
| 6 Quality | Modify implementation code to make a test pass; approve its own work |

That last row matters most. The reviewer fixing the code it reviews is how a quality gate becomes
a rubber stamp.

## 7. Escalation

| Condition | Behaviour |
|---|---|
| Gate fails | Stop. Report the gate and the reason. Never disable, never `--no-verify`. |
| Ownership conflict | Open a contract-first thread; do not edit the other bot's paths. |
| Cannot verify a claim | Move it to `unverified` and say so. Do not assert it. |
| Test fails and the fix is unclear | Investigate the code under test before the test. A failing test is usually correct. |
| Destructive op needed | Human approval, recorded in the receipt, before execution. |
| Contract change needed mid-implementation | Stop implementation. Amend the contract. Re-acknowledge. |

## 8. Stack

- **Languages:** Rust, Python, TypeScript/Deno, Kotlin, Swift
- **Edge/hosting:** Vercel
- **Infra:** Terraform, Kubernetes, GitHub Actions
- **Remote dev:** dedicated Linux dev machine — see `skills/platforms/remote-dev-machine/`
- **Models:** Opus for Bots 1 and 6 (design and review judgement), Sonnet for 2–5 (throughput)
