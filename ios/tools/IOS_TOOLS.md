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

Install the Python dependencies before invoking the tools (including on Linux):

```sh
python -m pip install -r ios/tools/requirements.txt
```

| Command | Where it runs | Exit |
| --- | --- | --- |
| `plist_lint --path FILE --json` | Linux, file or directory on disk | 0 ok, 1 blank usage or bad plist, 2 missing file |
| `entitlements_scan --path DIR` or `--diff BASE HEAD` | Linux | 0 ok, 1 unreadable plist or blank usage description, 2 missing args. Entitlement/usage values and their owning file (target) are tracked, not just key names |
| `spm_test_linux --package PATH` | `swift test` only if `swift` is on PATH | 3 skip when the toolchain is missing. `--dry-run` prints the argv and does not run it |
| `snapshot_diff --before --after --out` | sha256, plus PNG width/height | 0 written. Not a pixel diff. A renamed single file still pairs, so a rename is reported as changed-or-not rather than one add plus one remove |
| `xcodebuild_receipt --log PATH` | saved CI log only | does not invoke xcodebuild and does not boot a Simulator. `status` is `failed` if any `** ... FAILED **` banner appears anywhere in the log, not only the last one, and `scheme`/`destination` name the invocation that produced that banner |
| `device_screenshot` / `ui_dump` | executable of that exact name, `--serial` `--out` | 3 skip when the name is not on PATH. No stand-in image |
| `ui_tap` | executable named `ui_tap`, `--serial` `--out` `--target` | `--target` selects what to tap and is required; 3 skip when the name is not on PATH |
| `sim_drive boot` | macOS with `xcrun`. Flags: `--device-type`, `--runtime`, optional `--name`, `--out`, `--dry-run`, `--json` | 0 booted (prints `udid`). 2 missing `--out` on a real run, empty flags, or an unsafe/unreadable ledger. 3 `skipped: not on macOS` or `skipped: xcrun is not on PATH`. `--dry-run` is 0 and does not spawn |
| `sim_drive install` | macOS with `xcrun`. Flags: `--udid`, `--app`, `--dry-run`, `--json` | 0 installed. 1 `simctl` failed. 2 missing args. 3 skipped, as above |
| `sim_drive launch` | macOS with `xcrun`. Flags: `--udid`, `--bundle-id`, `--dry-run`, `--json` | 0 launched. 1 `simctl` failed. 2 missing args. 3 skipped, as above |
| `sim_drive screenshot` | macOS with `xcrun`. Flags: `--udid`, `--out`, `--dry-run`, `--json`. Runs `simctl io <udid> screenshot` and writes `<out>/screenshot.png` | 0 recorded. 1 `simctl` failed. 2 missing args or a path outside `--out`. 3 skipped, as above |
| `sim_drive record` | macOS with `xcrun`. Flags: `--udid`, `--out`, `--seconds`, `--dry-run`, `--json`. Runs `simctl io <udid> recordVideo`, sends SIGINT when `--seconds` elapses, and writes `<out>/recording-<unique-run-id>.mov` | 0 recorded only when the process exits 0 and the current MOV contains video sample descriptions and positive, consistent sample metadata referencing bytes inside `mdat`. 1 `simctl` failed, forced termination was required, or the current artifact is absent/invalid. 2 missing args, `--seconds` < 1, or a path outside `--out`. 3 skipped, as above |
| `sim_drive shutdown` | macOS with `xcrun`. Flags: `--udid`, `--created-udid`, `--out`, optional `--erase`, `--dry-run`, `--json` | 0 shutdown, or erased when `--erase` is set. 1 `simctl` failed. 2 the UDID was not created by `boot` in this `--out` ledger, `--udid` differs from `--created-udid`, `--out` is missing, or the ledger is unsafe/unreadable. 3 skipped, as above. This command never runs `simctl delete` |
| `xcodebuild_test` | macOS with `xcodebuild`. Flags: `--scheme`, `--destination`, `--out`, `--log`, repeatable `--only-testing`, `--dry-run`, `--json` | 0 the captured text log succeeded and `xcodebuild` exited 0. 1 the parsed log failed or `xcodebuild` exited nonzero, even with a success banner. 2 missing args, a log outside `--out`, or an unverified log with no result banner when `xcodebuild` exited 0. 3 `skipped: not on macOS` or `skipped: xcodebuild is not on PATH`. Simulator destinations (the destination string contains `simulator`) get `CODE_SIGNING_ALLOWED=NO` only. No other signing settings are added |
| `maestro_flow` | macOS with `maestro` on PATH. Flags: `--flow`, `--out`, `--dry-run`, `--json`. Runs `maestro test --format junit --test-output-dir <out> --output <out>/junit-<unique-run-id>.xml <flow>` and counts `<testcase>` results from that report only | 0 at least one case passed, JUnit reported no failures and Maestro exited 0. 1 a `<failure>` or `<error>` is present, or Maestro exited non-zero. 2 the flow file is missing, Maestro exited 0 without writing the current report, the report exceeds 20 MiB, or unsafe XML is rejected. 3 all cases were skipped with Maestro exit 0, `skipped: not on macOS` or `skipped: maestro is not on PATH`. Physical iPhones are Maestro's own refusal; this command does not target them |

`sim_drive boot` either creates a device (`xcrun simctl create <name> <device-type> <runtime>`, then `simctl boot <udid>`) or reuses a UDID already recorded in `<out>/created-udids.json` for the same device type and runtime. The JSON result includes that `udid`. `shutdown` and `--erase` read the same ledger. A UDID that is not in it is refused before any `simctl` process starts, including under `--dry-run`.

Ledger append operations hold a process-level lock on the output directory across the read-modify-write and publish JSON by atomic replacement. Reads refuse ledger symlinks and special files; ledger operations also refuse a symlink `--out` directory. Writes and replacement use names relative to the pinned directory descriptor, so swapping a ledger symlink or the output path cannot redirect a write to an outside file. If a device was created but its ledger could not be saved safely, the error result includes its `udid`.

Recording sends SIGINT at the requested duration so `simctl` can finalize its MOV. It allows a five-second finalization wait, then bounded terminate/kill fallback waits; a fallback is a failure, not a recorded result. The duration cap therefore allows additional cleanup time rather than promising immediate process death. Each invocation uses a fresh recording path and checks only that file; a stale recording cannot make the invocation pass, and earlier recordings are preserved. Validation requires `minf/stbl` video sample descriptions, consistent timing/count/chunk mappings and positive sample sizes, with every referenced sample range inside an `mdat` payload. Both ordinary MOV sample tables (including compact sizes and 64-bit offsets) and fragmented MOV track/run metadata are checked without reading or copying media payloads. An empty sample table is acceptable only when valid fragments supply actual video samples. These structural checks do not decode the codec; real Simulator recording and playback remain unverified until the macOS smoke check. The returned `artifact` names the current recording.

Each Xcode test invocation passes a fresh `<out>/TestResults-<unique-run-id>.xcresult` to `-resultBundlePath`, preserving earlier result bundles. The JSON `result_bundle` identifies the current path. Captured stdout and stderr are saved at the caller's `--log` and parsed as text regardless of its suffix, including a suffixless or `.json` filename. The nested `receipt` describes the parsed text and retains parser reasons and error lines; the wrapper also reports `tool_exit_code` and fails on any nonzero process exit. A success banner in the nested receipt cannot override that process failure.

Maestro's `--test-output-dir` controls artifacts; `--output` selects the JUnit report. Each invocation chooses a fresh report name under `--out` and reads only that report, so old passing or failing XML cannot determine a new result. Existing reports and artifacts are preserved. Passed, failed and skipped cases are counted separately; a skipped case is not counted as passed. When all cases are skipped and Maestro exited 0, the wrapper returns `status: "skipped"`, exit 3, the actual counts and a reason stating that no case executed. A mixed passed/skipped report can pass; a nonzero Maestro exit still fails. Malformed XML is ignored and, without usable cases in the current report, the invocation cannot pass.

JUnit parsing uses `defusedxml` and rejects DTD declarations, entities and external references. An unsafe current report returns JSON `status: "error"` with exit 2 and zero counts, even if Maestro exited 0. The `parse_junit_dir` API scans all XML reports recursively and likewise returns `status: "error"` if any report is unsafe, even alongside valid reports; it never silently skips hostile XML.

No App Store submission. No entitlement change in an app target. No signing identity, team or provisioning profile.

`README.md` is not used here. A bare `README.md` rule in `ownership.yaml` belongs to QUALITY at any depth.
