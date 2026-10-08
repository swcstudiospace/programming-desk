---
name: verify-systems
description: Prove a service or library change with a test that can fail. Use for SYSTEMS seat work on APIs, data, and backend code.
bots: [bot-01-systems-backend]
gates: [G-2]
---

# Verify systems

## L1 — Summary

**Reading the handler is not running it.** SYSTEMS proves the behavior with
a command that could have failed, then records that command.

**Decision tree:**

```
What changed?
├─ Python service or gate ──▶ pytest on that tree. A skip is not a pass.
├─ Rust crate with a Cargo.toml in the checkout ──▶ the three commands in
│     skills/platforms/rust/SKILL.md
├─ A bug report ──▶ reproduce first (expects_failure), then the same command.
└─ Needs a live data plane you cannot reach? ──▶ unverified names the plane.
```

Apply the proof standard in `skills/verify/SKILL.md`. Language rules are in
`skills/platforms/python/SKILL.md` and `skills/platforms/rust/SKILL.md`.

---

## Launch

Name the command from the tree you opened, not from memory.

| Tree | Command that exists for it |
|---|---|
| Desk gate suite | `python3 -m pytest ci/tests/ -v` |
| Gateway | `python3 -m pytest` with working directory `services/desk-gateway`. `services/desk-gateway/pyproject.toml` sets `testpaths = ["tests"]` and the tests live in `services/desk-gateway/tests` |
| A Rust crate whose checkout contains `Cargo.toml` | `cargo test`, `cargo clippy -- -D warnings`, and `cargo fmt --check` (`skills/platforms/rust/SKILL.md`) |

programming-desk at this skill's base has no root `Cargo.toml`. Do not report
`cargo test` as run here unless the checkout you are in actually has the
manifest. Python verification on changed modules is `pytest`, `ruff check`,
and `mypy` or `pyright` (`skills/platforms/python/SKILL.md`). A passing
import is not a passing test.

Fill `skills/verify/references/feature-map-template.md` when a person or a
client can exercise the behavior. Otherwise the "user path" is the call the
client makes, and Drive uses that call.

## Doctor

Install the test runner the manifest already declares. Do not add a
dependency to make a check look green (`skills/security/supply-chain/SKILL.md`).
If `pytest` is missing, the check did not run. Say so. Do not mask the
failure with a bypass G-2 rejects (`|| true`, `--passWithNoTests`).

A test that skips because a credential or a data plane is absent is
inconclusive. Read the output for the skip. Exit 0 with skipped tests does
not prove the skipped cases.

## Drive

1. Reproduce first when there is a bug (`skills/debugging/SKILL.md`). The
   failing command is claim evidence with `expects_failure`.
2. Re-run that same command after the fix. Then run the suite for the tree,
   not only the new file. One new file is not "the suite"
   (`skills/verification-receipts/SKILL.md` §3).
3. Check the side effect. If the call should write a row or enqueue a
   message, assert that write. A status code alone can pass while the write
   is missing.
4. Mock only at a boundary production already has (an upstream HTTP client
   behind an interface the service already uses). Do not mock the function
   you changed.
5. A dry run, a collect-only listing, or a type-check is not this drive.
   G-2 rejects `--dry-run` and a collect-only pytest. Type-check, lint, and
   runtime are different observations; cite the one you mean
   (`prompts/_shared/core-directives.xml`).

## Evidence

Save the pytest (or cargo) output under `.verify-evidence/<task-id>/`.
`output_tail` names the file and includes the pass or fail count you saw.
Do not commit the directory. Do not put a connection string or a token in
the tail (PD-4).

## Cleanup

Do not drop a table, truncate, or unbounded-delete as cleanup. Those match
the destructive patterns in `ci/gates/check_rollback.py` and need a recorded
approval (G-6). Leave fixtures the test created in the state the test is
supposed to leave them.

## Where it runs

| Runner | What it can host | Unverified line |
|---|---|---|
| Linux cloud agent | `python3 -m pytest ci/tests/ -v` and, when the dev extra is installed, the gateway tests | `gateway tests not run: dependency missing` |
| Self-hosted VPS runner | The same pytest commands. A data-plane test you cannot reach from here stays unrun | `no data plane: self-hosted VPS runner` |
| GitHub-hosted `ubuntu-latest` | Public-repo test jobs when a workflow runs them | `suite not run: no workflow in this checkout` |
| Ming's Mac | Private-repo suites the checkout can run | `suite not run: Ming's Mac` |

An emulator or a Simulator is not this skill. Hand those to
`skills/verify-android/SKILL.md` and `skills/verify-ios/SKILL.md`.

## Receipt mapping

| Observation | Field |
|---|---|
| The suite command and exit code | `commands[]`, cited by the claim that names that suite |
| A narrower file than the suite | the claim names the file. `unverified` names the suites you did not run |
| Reproduce-first failure | `expects_failure: true` and a non-zero exit on that command |
| Skipped tests | no claim that those cases passed. `unverified` quotes the skip reason |
| Lint or type-check | a separate command. Do not cite it for a behavior claim |
