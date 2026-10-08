# iOS tools

Python tools under `ios/tools/`. The checks in the first table run on Linux. They do not invoke `xcodebuild`, boot the Xcode Simulator, sign a binary, or talk to App Store Connect.

`sim_drive`, `xcodebuild_test` and `maestro_flow` are the macOS harness. On a Mac or a GitHub-hosted `macos-26` runner they drive Simulator, `xcodebuild test` and Maestro. On Linux, or when the binary is missing, each one exits 3 and the JSON `reason` is `skipped: <why>`. A skip is not a pass. `--dry-run` prints the argv as JSON and spawns nothing, including on Linux. `--json` is accepted for symmetry; output is always JSON. Evidence is written only under the `--out` directory the caller passes.

Device types and runtimes are whatever the caller passes. Nothing in these commands hard-codes a simulator name.

SPE-5161 asked for `ios/tools/README.md`. That file is not here. `ownership.yaml` has a bare `README.md` rule owned by QUALITY that matches at any depth and wins over `ios/**`, so G-1 would reject it. This note is the substitute until QUALITY moves that rule.

## Modules

| Tool | What it does | What it refuses |
| --- | --- | --- |
| `spm_linux.py` | `swift test` when `Package.swift` and a `swift` binary exist | A missing toolchain is `unverified`/`skipped`, not a pass |
| `plist_lint.py` | Blank usage strings, always-location without when-in-use, entitlements that embed a key | Does not submit the plist |
| `entitlements.py` | Entitlement and usage-string scan, or a diff of two trees; tracks values and the owning target, not just key names | Does not change an app target's entitlements |
| `snapshot_diff.py` | sha256 diff of two directories, two files, or a file against a directory, plus PNG width/height | Not a pixel or UI snapshot |
| `metavr_evidence.py` | Evidence JSON for `remote` or `metavr` runs | Any simulator kind. No MetaVR SDK is bundled |
| `metavr_bridge.py` | Wraps an on-PATH executable of the exact tool name | Invents no vendor SDK; a missing name is a skip |
| `xcodebuild_receipt.py` | Parses a CI log or JSON artifact | Does not launch `xcodebuild` |
| `sim_drive.py` | Wraps `xcrun simctl` (boot, install, launch, screenshot, record, shutdown) | Exit 3 on Linux or when `xcrun` is missing. Shutdown and erase only touch a UDID this run created |
| `xcodebuild_test.py` | Runs `xcodebuild test` and parses the log with `xcodebuild_receipt` | No signing identity, team or profile. Exit 3 on Linux or when `xcodebuild` is missing |
| `maestro_flow.py` | Runs `maestro test --format junit` and counts JUnit cases | Exit 3 on Linux or when `maestro` is missing. A JUnit failure is exit 1 |

## CLI

`python -m ios.tools <cmd>` from the repo root.

| Command | Where it runs | Exit |
| --- | --- | --- |
| `plist_lint --path FILE --json` | Linux, file or directory on disk | 0 ok, 1 blank usage or bad plist, 2 missing file |
| `entitlements_scan --path DIR` or `--diff BASE HEAD` | Linux | 0 ok, 1 unreadable plist or blank usage description, 2 missing args. Entitlement/usage values and their owning file (target) are tracked, not just key names |
| `spm_test_linux --package PATH` | `swift test` only if `swift` is on PATH | 3 skip when the toolchain is missing. `--dry-run` prints the argv and does not run it |
| `snapshot_diff --before --after --out` | sha256, plus PNG width/height | 0 written. Not a pixel diff. A renamed single file still pairs, so a rename is reported as changed-or-not rather than one add plus one remove |
| `xcodebuild_receipt --log PATH` | saved CI log only | does not invoke xcodebuild and does not boot a Simulator. `status` is `failed` if any `** ... FAILED **` banner appears anywhere in the log, not only the last one, and `scheme`/`destination` name the invocation that produced that banner |
| `device_screenshot` / `ui_dump` | executable of that exact name, `--serial` `--out` | 3 skip when the name is not on PATH. No stand-in image |
| `ui_tap` | executable named `ui_tap`, `--serial` `--out` `--target` | `--target` selects what to tap and is required; 3 skip when the name is not on PATH |
| `sim_drive boot` | macOS with `xcrun`. Flags: `--device-type`, `--runtime`, optional `--name`, `--out`, `--dry-run`, `--json` | 0 booted (prints `udid`). 2 missing `--out` on a real run, or empty flags. 3 `skipped: not on macOS` or `skipped: xcrun is not on PATH`. `--dry-run` is 0 and does not spawn |
| `sim_drive install` | macOS with `xcrun`. Flags: `--udid`, `--app`, `--dry-run`, `--json` | 0 installed. 1 `simctl` failed. 2 missing args. 3 skipped, as above |
| `sim_drive launch` | macOS with `xcrun`. Flags: `--udid`, `--bundle-id`, `--dry-run`, `--json` | 0 launched. 1 `simctl` failed. 2 missing args. 3 skipped, as above |
| `sim_drive screenshot` | macOS with `xcrun`. Flags: `--udid`, `--out`, `--dry-run`, `--json`. Runs `simctl io <udid> screenshot` and writes `<out>/screenshot.png` | 0 recorded. 1 `simctl` failed. 2 missing args or a path outside `--out`. 3 skipped, as above |
| `sim_drive record` | macOS with `xcrun`. Flags: `--udid`, `--out`, `--seconds`, `--dry-run`, `--json`. Runs `simctl io <udid> recordVideo` and kills it when `--seconds` elapses. Writes `<out>/recording.mov` | 0 recorded, including when the cap stops the process. 1 `simctl` failed before the cap. 2 missing args, `--seconds` < 1, or a path outside `--out`. 3 skipped, as above |
| `sim_drive shutdown` | macOS with `xcrun`. Flags: `--udid`, `--created-udid`, `--out`, optional `--erase`, `--dry-run`, `--json` | 0 shutdown, or erased when `--erase` is set. 1 `simctl` failed. 2 the UDID was not created by `boot` in this `--out` ledger, `--udid` differs from `--created-udid`, or `--out` is missing. 3 skipped, as above. This command never runs `simctl delete` |
| `xcodebuild_test` | macOS with `xcodebuild`. Flags: `--scheme`, `--destination`, `--out`, `--log`, repeatable `--only-testing`, `--dry-run`, `--json` | 0 the parsed log succeeded. 1 the parsed log failed. 2 missing args, a log outside `--out`, or an unverified log with no result banner. 3 `skipped: not on macOS` or `skipped: xcodebuild is not on PATH`. Simulator destinations (the destination string contains `simulator`) get `CODE_SIGNING_ALLOWED=NO` only. No other signing settings are added |
| `maestro_flow` | macOS with `maestro` on PATH. Flags: `--flow`, `--out`, `--dry-run`, `--json`. Runs `maestro test --format junit --test-output-dir <out> <flow>` and counts `<testcase>` results | 0 JUnit reported no failures and Maestro exited 0. 1 a `<failure>` or `<error>` is present, or Maestro exited non-zero. 2 the flow file is missing, or Maestro exited 0 without writing JUnit XML. 3 `skipped: not on macOS` or `skipped: maestro is not on PATH`. Physical iPhones are Maestro's own refusal; this command does not target them |

`sim_drive boot` either creates a device (`xcrun simctl create <name> <device-type> <runtime>`, then `simctl boot <udid>`) or reuses a UDID already recorded in `<out>/created-udids.json` for the same device type and runtime. The JSON result includes that `udid`. `shutdown` and `--erase` read the same ledger. A UDID that is not in it is refused before any `simctl` process starts, including under `--dry-run`.

No App Store submission. No entitlement change in an app target. No signing identity, team or provisioning profile.

`README.md` is not used here. A bare `README.md` rule in `ownership.yaml` belongs to QUALITY at any depth.
