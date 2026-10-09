---
name: verify
description: Proof standard for a completion claim. Use before saying a change works, and load the seat's platform skill to run it.
bots: [bot-00-programming-lead, bot-06-quality-security]
gates: [G-2]
---

# Verify

## L1 — Summary

**Prove the change on the real artifact.** A compile, a type-check, or a
convincing reading is not that proof. The receipt is where the proof lands.

**Decision tree:**

```
About to claim the change works?
├─ NO ──▶ Do not write the claim.
└─ YES
    ├─ Which seat owns the artifact? Open that platform skill
    │   (verify-web, verify-desktop, verify-ios, verify-android,
    │    verify-infra, verify-systems).
    ├─ Can this runner execute that skill's Drive?
    │   ├─ NO ──▶ Stop. Put the gap in unverified. Do not convert it to a pass.
    │   └─ YES ──▶ Launch, Doctor, Drive, Evidence, Cleanup, then Receipt mapping.
    └─ Did a step fail to run? Report it inconclusive under unverified.
```

Method adapted from pstack (MIT, Lauren Tan, github.com/cursor/plugins/tree/main/pstack).

---

## Launch

Open the platform skill for the artifact, then copy
`skills/verify/references/feature-map-template.md` once per user-visible
feature. Fill it before Drive. A feature with no map has no scripted path, so
a later "it works" claim has nothing a reviewer can re-run (G-2).

Seats load their skill from the `seat_verification` block in
`prompts/_shared/core-directives.xml`. LEAD and QUALITY load this router.
SYSTEMS, WEB, ANDROID, IOS and INFRA load the platform skill named there.
Seat sources under `prompts/bot-00-programming-lead.xml`,
`prompts/bot-01-systems-backend.xml`, `prompts/bot-02-web-edge.xml`,
`prompts/bot-03-android.xml`, `prompts/bot-04-ios.xml`,
`prompts/bot-05-infrastructure.xml` and
`prompts/bot-06-quality-security.xml` stay untouched: those files are
seat-owned (PD-2).

## Doctor

Confirm the runner can do what Drive is about to claim. Read the platform
skill's **Where it runs** and compare it to the machine you are on. A Linux
cloud agent is not a macOS simulator host. The self-hosted VPS runner has no
KVM and no iOS tooling. If the runner cannot host the check, Doctor ends
here: the check is inconclusive, and the receipt lists it under `unverified`
with the runner name. Do not start Drive in order to manufacture a green
exit code (PD-3).

## Drive

Apply this proof standard, in order:

1. **Real user path.** Exercise the path a person takes. "It compiles" is a
   different observation and does not substitute (see
   `skills/verification-receipts/SKILL.md` §1).
2. **Action and resulting state.** Record what you did and the state that
   followed. A screenshot with no preceding action, or an action with no
   observed state, is half a proof.
3. **Side effects.** Check the write the path was supposed to cause: the row,
   the file, the message, the deployment status. The screen can look right
   while the write never happened.
4. **Mocks only at a production boundary.** A mock is allowed where the
   production system is already isolated behind that boundary. A mock placed
   where production has no boundary proves the mock.
5. **Read what a dry run skips.** A dry run that prints an argv and exits 0
   did not execute. `ios/tools/IOS_TOOLS.md` documents
   `spm_test_linux --dry-run` as printing argv and not running. G-2 rejects a
   receipt command that contains `--dry-run`
   (`ci/gates/check_receipt.py`), so the dry run is not evidence. If the real
   command did not run, say so under `unverified`.

Reproduce a bug before fixing it (`skills/debugging/SKILL.md`). The first run
is the one that fails. The claim for that run sets `expects_failure`.

## Evidence

Write artifacts under `.verify-evidence/<task-id>/` in the working tree.
Never commit that directory; `.gitignore` ignores it. Preserve concise
observed result, action and resulting-state excerpts in the receipt's
`output_tail`, including the pass/fail or skip result where applicable.
For captures or logs needed beyond that excerpt, upload them to durable
storage and record stable artifact references only after the upload
succeeds. A transient local path alone is not durable evidence; neither is
an expired signed download URL.

CI uploads the folder only when a workflow for this family exists. This
checkout has no such workflow yet; do not assume an upload or invent one in
a seat you do not own. An artifact you did not write is not evidence. Name
it only after the command that produced it.

## Cleanup

Leave the tree without the evidence directory staged. Before deleting
transient evidence, ensure the receipt retains concise result/action/state
excerpts in `output_tail` and/or stable references to successfully uploaded
durable artifacts sufficient for the claim. If not, retain the local copy;
do not reduce evidence to dead paths. Do not delete a reviewer's copy of an
artifact that already landed in CI or external simulator/device resources.

This family does not submit to an app store, sign a binary, redeploy, or
change Railway variables. Those are G-6 operations (`desk_railway_redeploy`
and store actions stay approval-gated). Cleanup is not a quiet way to do them.

## Where it runs

| Runner | What this router can honestly claim |
|---|---|
| Cursor cloud agent (Linux VM) | Gate commands, pytest, and Linux-safe helpers that exist in the checkout. No iOS Simulator. An Android emulator here is not a reliable pass. |
| Self-hosted VPS runner (`[self-hosted, Linux, X64]`) | Same Linux limits. No `/dev/kvm`, so no accelerated emulator. No iOS tooling. |
| GitHub-hosted `macos-26` (Xcode 26.6) | Public-repo iOS simulator runs. Private repos do not use this runner. |
| GitHub-hosted `ubuntu-latest` with KVM | Public-repo Android emulator runs. Private repos do not use this runner. |
| Ming's Mac (self-hosted) | Private-repo iOS and Android fallback. Paid device clouds are off. |

The platform skill names the unverified line when its runner is missing. The
phrase for a simulator that never booted is `no simulator: Linux cloud agent`.

## Receipt mapping

Map the run onto `skills/verification-receipts/SKILL.md`. The gate reads the
JSON, not the prose around it.

| Proof | Receipt field |
|---|---|
| A replayable shell/CLI command you actually ran | `commands[]` with the real `cmd`, observed process `exit_code`, and `output_tail` containing concise result/action/state excerpts and/or stable uploaded durable artifact references |
| What that command proves | `claims[]` with `evidence_command_index` pointing at that command |
| The reproduce-first run, which should fail | the same claim with `expects_failure: true`, and a non-zero `exit_code` |
| A check that did not run | `unverified`, specific, for example `no simulator: Linux cloud agent` |
| Anything you did not execute | do not claim it. Inconclusive stays in `unverified` |
| A tool-only MCP/roster observation | keep the tool name, arguments and redacted result separately from `commands[]`; the command-backed proof claim stays `unverified` until a replayable shell/CLI command actually runs |

Do not invent a shell command from a tool name or infer process exit 0 from
a successful tool response. Reuse an existing authenticated invocation
route or CLI when available, recording working directory and named
environment prerequisites without secret values. Inspect the actual result
as well as the observed process exit: transport success is not proof that
the requested check succeeded. `commands[]` contains executions, not tool
transcripts or commands you only intend to run.

`approved_by` is never the authoring bot. When QUALITY authors the change,
the stamp comes from LEAD or a human and stays absent until that review
(`docs/quality-gates.md`).

The structural check for this family is
`python3 -m pytest ci/tests/test_verify_skills.py -v`. It fails when a skill
is missing a required section or cites a repo path that does not exist
outside a fenced block marked `example`.
