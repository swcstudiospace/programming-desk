# Skills

Progressive-disclosure capability packs. A bot loads the smallest amount of guidance that lets it
act correctly, and goes deeper only when its decision tree says to.

## Levels

| Level | Content | When |
|---|---|---|
| **L1 — Summary** | First ~30 lines: what it does, when it applies, the decision tree | On load |
| **L2 — Method** | The body: procedure, rubrics, failure modes | When executing |
| **L3 — References** | `references/` files: deep detail, edge cases | Only when L2 points there |

A bot cites which level informed a non-obvious decision, so a reviewer can tell whether a mistake
came from the skill or from its application.

## Map

| Skill | Bots | Purpose |
|---|---|---|
| `gotxcot-uplift` | LEAD | First XML uplift, GoT 5–8, sequential CoT 4–8 steps/node, kickoff, second uplift with URLs |
| `trackplan-dispatch` | LEAD | Dispatch the second-uplift XML to Cursor Cloud Agent (default) or Hermes |
| `greptile-merge-gate` | QUALITY | Merge-claim Greptile gate. Does not replace G-1…G-6 — the split is in `docs/quality-gates.md` § *Greptile is not a gate* |
| `verification-receipts` | all | The G-2 artefact. **Always loaded.** |
| `contract-first-changes` | 1, 6 | Breaking-change analysis, consumer impact |
| `code-review` | 6 | Review order, what to flag, what to let go |
| `debugging` | all | Reproduce → isolate → fix → verify |
| `platforms/rust` | 1 | Ownership, errors, async, testing |
| `platforms/python` | 1 | Typing, packaging, testing, async |
| `platforms/deno-typescript` | 2 | Permissions, modules, types |
| `platforms/android` | 3 | Compose, coroutines, lifecycle, release |
| `platforms/ios` | 4 | SwiftUI, concurrency, App Review |
| `platforms/vercel` | 2 | Edge runtime, deploys, rollback |
| `platforms/terraform-k8s` | 5 | State, plans, progressive delivery |
| `platforms/remote-dev-machine` | 5, all | The shared dev box: access and safety |
| `security/secrets-handling` | 6, all | Detection, rotation, exposure response |
| `security/supply-chain` | 6 | Dependency provenance, licences, CVEs |

## Authoring rules

1. **L1 must be sufficient to decide** whether L2 is needed.
2. **Every rule states its consequence.** "Do X" is weaker than "Do X, because otherwise Y".
3. **Worked examples over abstractions.** One good and one bad beats three paragraphs.
4. **Reference the gate ID** where a rule maps to one, so gate and skill change together.
5. **No duplication.** A rule needed by two skills belongs in `_shared/core-directives.xml`.

## Growth path

Add a skill when a bot has made the same class of mistake **twice**. Skills written ahead of
evidence encode guesses.

Likely next, in the order they usually earn their place: `performance-profiling`,
`incident-response`, `database-design`, `api-versioning`, `accessibility`, and per-service
`domains/<service>` skills once services grow their own conventions.
