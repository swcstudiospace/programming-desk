---
name: verify-android
description: Prove an Android change on a device at minSdk, and treat a skipped Gradle run as not run. Use for ANDROID seat work.
bots: [bot-03-android]
gates: [G-2]
---

# Verify Android

## L1 — Summary

**Exit 0 is not a pass when the output says skipped.** Android tools print
`skipped:` and exit 0 when no device or wrapper is present. Read the output.

**Decision tree:**

```
What are you about to claim?
├─ "unit tests ran" ──▶ The output must not be the skip line. Otherwise unverified.
├─ "ran on a device at minSdk" ──▶ Needs KVM (public ubuntu) or Ming's Mac.
│     No KVM ──▶ no emulator: no KVM
└─ "signed" or "Play submission" ──▶ Stop. That is G-6.
```

Apply the proof standard in `skills/verify/SKILL.md`. The checks you are
aiming at are in `skills/platforms/android/SKILL.md`.

---

## Launch

Read `android/tools/USAGE.md`. The entry point is `python -m android.tools`.
This desk checkout has no Gradle wrapper, so `unit_test` here cannot execute
an app's tests. No Android product repo is in this wave. Fill
`skills/verify/references/feature-map-template.md` in the product checkout
before driving a screen. Maestro CLI 2.11.0 drives an emulator when one is
actually booted. Do not add a workflow in this unit. Any Action a later
workflow uses to boot an emulator is pinned by commit SHA (`SECURITY.md`
§6), not by a floating tag.

## Doctor

| Command | What a green exit can hide |
|---|---|
| `python -m android.tools unit_test --module PATH` | Prints `skipped: no gradlew found (unit_test requires a Gradle wrapper in cwd or --module)` and exits 0 when no wrapper is present |
| `python -m android.tools adb_devices --json` | A machine with no device is a skip line and exit 0, not a device pass |
| `python -m android.tools emu_boot --avd NAME --timeout-sec N` | Without a device binary this prints `skipped:` and exits 0. Do not record the dry-run form; G-2 rejects `--dry-run` |
| `python -m android.tools instrumented_run --serial SERIAL --class CLASS` | Needs a connected device. A skip is not an instrumented run |

`android/tools/USAGE.md` states the rule: missing binary or no connected
device prints `skipped: <reason>` and exits 0. Doctor fails the claim when
that line is present, whatever the exit code was.

Public emulator runs use GitHub-hosted `ubuntu-latest` with KVM enabled.
The self-hosted VPS runner has no `/dev/kvm`. A Cursor cloud agent's nested
KVM is not a reliable emulator host. Private repos use Ming's Mac. Paid
device clouds are off.

## Drive

1. On a product tree that has a wrapper, run `testDebugUnitTest`, `lintDebug`
   and `assembleDebug` (`skills/platforms/android/SKILL.md`). A release claim
   also needs the R8 check that skill names, because R8 failures show up in
   release only.
2. Run on a device or emulator at minSdk. Exercise the user path. Record the
   action and the resulting screen, and the side effect (the row saved, the
   permission state). Rotate, and cover process death the way that skill
   describes, when the device is real enough to kill.
3. If `python -m android.tools` printed `skipped:`, you did not drive. Record
   the output under `unverified`. Do not file a claim that cites that command
   as a pass.
4. Do not sign, and do not submit to Play.

## Evidence

Save the Gradle output, the `skipped:` line when that is what you got, and
any screenshot under `.verify-evidence/<task-id>/`. `output_tail` quotes the
skip line or names the artifact. Do not commit the directory. A skip line
that is only in your head did not happen; paste the line you saw.

## Cleanup

Stop an emulator you started, on a runner that has one. Do not sign and do
not upload a bundle. Store submission stays approval-gated (G-6).

## Where it runs

| Runner | What it can host | Unverified line |
|---|---|---|
| Linux cloud agent | `android.tools` introspection. Emulator boot is not a reliable pass | `no emulator: Linux cloud agent` |
| Self-hosted VPS runner | Same. No `/dev/kvm` | `no emulator: no KVM` |
| GitHub-hosted `ubuntu-latest` with KVM | Public-repo emulator at minSdk | `no emulator: KVM not enabled` |
| Ming's Mac | Private-repo emulator or device | `no device at minSdk: Ming's Mac` |
| `macos-26` | Not the Android path for this family | `Android emulator not run: this runner is the iOS host` |

## Receipt mapping

| Observation | Field |
|---|---|
| `testDebugUnitTest`, `lintDebug`, `assembleDebug` | one `commands` entry each, or one command whose text shows all three ran. Citing assemble for a "ran on device" claim is the mismatch in `skills/verification-receipts/SKILL.md` §3 |
| Output contains `skipped:` | no passing claim on that command. `unverified` quotes the reason |
| minSdk device or emulator | its own command. The claim names the API level you actually booted |
| Reproduce-first failure | `expects_failure: true` |
| Emulator you could not boot | `unverified` with the row above |
