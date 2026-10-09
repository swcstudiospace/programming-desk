---
name: verify-android
description: Prove an Android change on a device at minSdk, and treat a skipped Gradle run as not run. Use for ANDROID seat work.
bots: [bot-03-android]
gates: [G-2]
---

# Verify Android

## L1 — Summary

**Exit 0 is not proof of a ready device or a test run.** Android tools may
print `skipped:`, but an empty or offline device list can also exit 0
without that line. Read the output and the device states.

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
| `python -m android.tools adb_devices --json` | Can return `[]` or rows whose `state` is `offline` / `unauthorized` with exit 0 and no `skipped:`. Require at least one `state: device` row and the requested serial in that state |
| `python -m android.tools emu_boot --avd NAME --timeout-sec N` | Without a device binary this prints `skipped:` and exits 0. Do not record the dry-run form; G-2 rejects `--dry-run` |
| `python -m android.tools instrumented_run --serial SERIAL --class CLASS` | Needs a connected device. A skip is not an instrumented run |

`android/tools/USAGE.md` documents missing-binary skip lines. Doctor fails
the claim when `skipped:` is present, whatever the exit code. For
`adb_devices`, absence of that line is not enough: the actual implementation
in `android/tools/adb.py` returns the parsed list, including empty or
non-ready rows. Stop and record `unverified` unless at least one row has
`state: device` and the serial requested for Drive is one of those rows.

Public emulator runs use GitHub-hosted `ubuntu-latest` with KVM enabled.
The self-hosted VPS runner has no `/dev/kvm`. A Cursor cloud agent's nested
KVM is not a reliable emulator host. Private repos use Ming's Mac. Paid
device clouds are off.

## Drive

1. On a product tree that has a wrapper, run `testDebugUnitTest`, `lintDebug`
   and `assembleDebug` (`skills/platforms/android/SKILL.md`). A release claim
   also needs the R8 check that skill names, because R8 failures show up in
   release only.
2. After boot, run `python -m android.tools adb_devices --json` and confirm
   the requested serial is present with `state: device`; use that exact
   serial for the device commands. An empty list, only offline/unauthorized
   rows, or a different ready serial does not permit Drive. Run on that
   device or emulator at minSdk and record its observed API level. Exercise
   the user path. Record the action and resulting screen, and the side
   effect (the row saved, the permission state). Rotate and cover process
   death the way the platform skill describes, when the device is real
   enough to kill.
3. If `python -m android.tools` printed `skipped:`, you did not drive. Record
   the output under `unverified`. Do not file a claim that cites that command
   as a pass.
4. Do not sign, and do not submit to Play.

## Evidence

Save Gradle output, the actual device-list JSON, any observed `skipped:`
line, and screenshots under `.verify-evidence/<task-id>/`. `output_tail`
quotes the result, device serial/state or skip reason, not only an artifact
path. Preserve durable evidence before cleanup as `skills/verify/SKILL.md`
requires. Do not commit the directory or invent a skip line you did not see.

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
| minSdk device or emulator | its own executed command. Record the requested serial's `state: device` row and observed API level; an empty/offline list or another serial leaves the device claim `unverified` |
| Reproduce-first failure | `expects_failure: true` |
| Emulator you could not boot | `unverified` with the row above |
