---
name: verify-ios
description: Prove an iOS change on the minimum supported OS, and keep Linux checks from standing in for a simulator. Use for IOS seat work.
bots: [bot-04-ios]
gates: [G-2]
---

# Verify iOS

## L1 — Summary

**Linux can lint a plist. It cannot boot a Simulator.** Say which of the two
you did. The receipt has to be able to tell them apart.

**Decision tree:**

```
What are you about to claim?
├─ "plist / entitlements / SPM on Linux" ──▶ ios/tools only. Exit 3 is a skip.
├─ "tests ran on the minimum iOS" ──▶ needs macos-26 or Ming's Mac.
│     A Linux agent writes: no simulator: Linux cloud agent
└─ "submitted" or "signed" ──▶ Stop. Store and signing stay G-6.
```

Apply the proof standard in `skills/verify/SKILL.md`. The product rules you
are proving against are in `skills/platforms/ios/SKILL.md`.

---

## Launch

Read `ios/tools/IOS_TOOLS.md` before inventing a command. The Linux entry
point is `python -m ios.tools`. Fill
`skills/verify/references/feature-map-template.md` for each screen a person
can reach. No iOS product repo is in this wave, so a missing app tree is
inconclusive, not a skipped pass. Maestro, when a simulator run exists, is
CLI 2.11.0. Maestro does not drive a physical iPhone. Do not add a workflow
in this unit.

## Doctor

On Linux, confirm you are not about to describe a Simulator run. These
commands do not launch `xcodebuild` and do not boot a Simulator
(`ios/tools/IOS_TOOLS.md`):

| Command | Honest result |
|---|---|
| `python -m ios.tools plist_lint --path FILE --json` | 0 ok, 1 blank usage or bad plist, 2 missing file |
| `python -m ios.tools entitlements_scan --path DIR` | 0 ok, 1 unreadable plist or blank usage, 2 missing args |
| `python -m ios.tools spm_test_linux --package PATH` | Runs `swift test` only when `swift` is on PATH. Exit 3 when the toolchain is missing. `status` `skipped` means the tests did not run |
| `python -m ios.tools snapshot_diff --before BEFORE --after AFTER --out OUT` | sha256 plus PNG width and height. Not a pixel diff |
| `python -m ios.tools xcodebuild_receipt --log PATH` | Parses a log CI already saved. `xcodebuild_invoked` stays false |
| `python -m ios.tools device_screenshot --serial SERIAL --out OUT` | Exit 3 when `device_screenshot` is not on PATH. The wrapper writes no stand-in image |

`spm_test_linux --dry-run` prints the argv and sets `tests_ran` false, and it
exits 0. That is not a pass. G-2 rejects `--dry-run` in a receipt command, so
do not record it as evidence.

A Simulator or device claim requires Doctor to see the OS. Public repos use
GitHub-hosted `macos-26` (Xcode 26.6). Private repos use Ming's Mac. Paid
device clouds are off.

## Drive

1. Build Debug and build Release, then run tests, then run on the minimum
   supported iOS (`skills/platforms/ios/SKILL.md`). Look at the UI. A warning
   you suppressed to clear the build is not a drive (PD-3).
2. On Linux, run the `ios/tools` command that matches the claim and read the
   JSON. Exit 3, or `status` `skipped` / `unverified`, means the check did
   not run. Put that in `unverified`. Do not cite the exit code alone.
3. `xcodebuild_receipt` is evidence of a log you already have. It is not a
   substitute for the run that produced the log. If you have no log, you do
   not have a Simulator result.
4. When a `macos-26` or Mac run exists, drive the user path (Maestro CLI
   2.11.0 on a simulator, or the interaction you performed) and record the
   action plus the resulting screen. Check the side effect, not only the
   pixels.
5. Do not sign, and do not submit to App Store Connect.

## Evidence

Write the JSON from `ios/tools` and any simulator capture under
`.verify-evidence/<task-id>/`. Preserve concise result, action and state
excerpts in `output_tail` and/or stable references to uploaded durable
artifacts as `skills/verify/SKILL.md` requires. A local filename alone is
insufficient. Do not commit the directory. A missing screenshot must stay
missing: the MetaVR wrapper does not invent one (`ios/tools/IOS_TOOLS.md`).

## Cleanup

Do not leave a signed archive or a store submission behind. This skill does
not perform either. Remove transient local log/capture copies only after
their concise result/action/state excerpts are saved in the receipt's
`output_tail`, or their upload succeeded and stable durable artifact
references are recorded. Naming a soon-to-be-deleted local file is not
preservation. If neither is available, retain the local evidence. Do not
erase or delete simulators, devices, or other external resources as cleanup.

## Where it runs

| Runner | What it can host | Unverified line |
|---|---|---|
| Linux cloud agent | `ios/tools` only | `no simulator: Linux cloud agent` |
| Self-hosted VPS runner | `ios/tools` only. No iOS tooling on that host | `no simulator: self-hosted VPS runner` |
| GitHub-hosted `macos-26` (Xcode 26.6) | Public-repo Simulator, Debug and Release | `simulator not run: private repo uses Ming's Mac` |
| Ming's Mac | Private-repo Simulator and device | `no simulator: Ming's Mac` |
| `ubuntu-latest` | Not an iOS host | `no simulator: ubuntu runner` |

## Receipt mapping

| Observation | Field |
|---|---|
| An `ios/tools` command and the exit code you saw | `commands[]`. The claim matches the status field, not only the exit |
| Exit 3 or `status: skipped` | no passing claim. `unverified` names the missing toolchain or binary |
| Debug build, Release build, minimum-OS run | three commands, or one command that clearly ran all three. A single lint is not the three |
| Reproduce-first failure | `expects_failure: true` |
| Simulator you did not boot | `unverified` with the row above |
